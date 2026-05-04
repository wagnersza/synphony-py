"""Jira tracker adapter backed by the Atlassian CLI (`acli`)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Collection, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from synphony.errors import AcliNotFoundError, JiraQueryFailedError, TrackerParseError
from synphony.models import Issue

AcliRunner = Callable[[list[str], float], str]
_ISSUE_FIELDS = "key,summary,status,description,priority,labels,issuelinks,created,updated"
_DEFAULT_LIMIT = "50"


class JiraAcliTracker:
    """Production tracker adapter that shells out to `acli` and parses JSON output."""

    def __init__(
        self,
        *,
        jql: str,
        active_state_names: Collection[str],
        acli_path: str = "acli",
        timeout_s: float = 30,
        runner: AcliRunner | None = None,
    ) -> None:
        self._jql = jql
        self._active_state_names = tuple(active_state_names)
        self._acli_path = acli_path
        self._timeout_s = timeout_s
        self._runner = runner or _run_acli

    def fetch_candidate_issues(self) -> list[Issue]:
        return self.fetch_issues_by_states(self._active_state_names)

    def fetch_issues_by_states(self, state_names: Collection[str]) -> list[Issue]:
        command = [
            self._acli_path,
            "jira",
            "workitem",
            "search",
            "--jql",
            _with_state_filter(self._jql, state_names),
            "--fields",
            _ISSUE_FIELDS,
            "--limit",
            _DEFAULT_LIMIT,
            "--json",
        ]
        return parse_issue_list(self._run_json(command))

    def fetch_issue_states_by_ids(self, issue_ids: Collection[str]) -> dict[str, str]:
        states: dict[str, str] = {}
        for issue_id in issue_ids:
            command = [
                self._acli_path,
                "jira",
                "workitem",
                "view",
                issue_id,
                "--fields",
                _ISSUE_FIELDS,
                "--json",
            ]
            issue = parse_issue(self._run_json(command))
            states[issue.id] = issue.state
        return states

    def _run_json(self, command: list[str]) -> Any:
        try:
            output = self._runner(command, self._timeout_s)
        except FileNotFoundError as exc:
            raise AcliNotFoundError() from exc
        except subprocess.TimeoutExpired as exc:
            raise JiraQueryFailedError(
                "acli command timed out",
                details={"command": command, "timeout_s": self._timeout_s},
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise JiraQueryFailedError(
                "acli command failed",
                details={
                    "command": command,
                    "returncode": exc.returncode,
                    "stderr": _decode_process_output(exc.stderr),
                },
            ) from exc

        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise TrackerParseError("acli did not return valid JSON") from exc


def parse_issue_list(payload: Any) -> list[Issue]:
    if isinstance(payload, list):
        raw_issues = payload
    elif isinstance(payload, Mapping):
        issues_value = payload.get("issues", payload.get("values", []))
        if not isinstance(issues_value, list):
            raise TrackerParseError("Jira issue list payload must contain a list")
        raw_issues = issues_value
    else:
        raise TrackerParseError("Jira issue list payload must be a list or object")

    return [parse_issue(raw_issue) for raw_issue in raw_issues]


def parse_issue(payload: Any) -> Issue:
    if not isinstance(payload, Mapping):
        raise TrackerParseError("Jira issue payload must be an object")

    fields = _mapping_value(payload, "fields")
    source: Mapping[str, Any] = fields or payload

    issue_id = _required_str(payload, "id")
    key = _required_str(payload, "key")
    title = _optional_str(source, "summary") or key
    status = _status_name(source.get("status"))
    created_at = _parse_datetime(_optional_str(source, "created"))
    updated_at = _parse_datetime(_optional_str(source, "updated"))
    priority = _priority_value(source.get("priority"))
    labels = _string_tuple(source.get("labels"))
    blocked_by = _blocked_by(source)
    description = _optional_str(source, "description")
    url = _optional_str(payload, "self") or _optional_str(source, "url")

    return Issue(
        id=issue_id,
        identifier=key,
        title=title,
        state=status,
        created_at=created_at,
        updated_at=updated_at,
        description=description,
        priority=priority,
        labels=labels,
        url=url,
        blocked_by=blocked_by,
        raw=dict(payload),
    )


def _run_acli(command: list[str], timeout_s: float) -> str:
    completed = subprocess.run(  # noqa: S603 - command is assembled from trusted config values.
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return completed.stdout


def _with_state_filter(jql: str, state_names: Collection[str]) -> str:
    states = tuple(state_names)
    if not states:
        return jql
    quoted_states = ", ".join(_quote_jql_string(state) for state in states)
    return f"{jql} AND status in ({quoted_states})"


def _quote_jql_string(value: str) -> str:
    return '"' + value.replace('"', '\\"') + '"'


def _status_name(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, Mapping):
        name = value.get("name")
        if isinstance(name, str) and name.strip():
            return name
    raise TrackerParseError("Jira issue status is required")


def _priority_value(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    if isinstance(value, Mapping):
        raw = value.get("id", value.get("value"))
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return None


def _blocked_by(source: Mapping[str, Any]) -> tuple[str, ...]:
    explicit = source.get("blocked_by")
    if explicit is not None:
        return _string_tuple(explicit)

    blocked: list[str] = []
    links = source.get("issuelinks", [])
    if not isinstance(links, Sequence) or isinstance(links, str):
        return ()

    for link in links:
        if not isinstance(link, Mapping):
            continue
        link_type = _mapping_value(link, "type")
        inward = _optional_str(link_type, "inward") if link_type else None
        if inward and "blocked by" in inward.casefold():
            inward_issue = _mapping_value(link, "inwardIssue")
            if inward_issue:
                key = _optional_str(inward_issue, "key")
                if key:
                    blocked.append(key)

    return tuple(blocked)


def _parse_datetime(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)

    normalized = value
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    elif len(normalized) >= 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _required_str(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TrackerParseError(f"Jira issue {key} is required")
    return value


def _optional_str(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return None


def _mapping_value(payload: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = payload.get(key)
    if isinstance(value, Mapping):
        return value
    return None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _decode_process_output(value: object) -> str | None:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return value
    return None
