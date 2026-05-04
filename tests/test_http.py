from __future__ import annotations

from datetime import UTC, datetime, timedelta

from synphony.http import issue_payload, runtime_state_payload
from synphony.models import Issue, LiveSession, RetryEntry, RunAttempt, RuntimeState, Workspace


def test_runtime_state_payload_exposes_running_and_retry_state() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    issue = _issue(now)
    attempt = RunAttempt(issue_id=issue.id, issue_identifier=issue.identifier, attempt=2)
    state = RuntimeState(
        claimed_issue_ids={issue.id},
        running={
            issue.id: LiveSession(
                issue=issue,
                workspace=Workspace(path="/tmp/demo-1", key="demo-1", created_now=False),
                attempt=attempt,
                provider="codex",
                session_id="codex:session",
                started_at=now,
                last_event_at=now,
            )
        },
        retries=[
            RetryEntry(
                issue=issue,
                attempt=attempt,
                next_retry_at=now + timedelta(seconds=30),
                reason="agent_stalled",
                backoff_ms=30000,
            )
        ],
    )

    payload = runtime_state_payload(state)

    assert payload["claimed_issue_ids"] == ["10001"]
    assert payload["running"][0]["issue_identifier"] == "DEMO-1"
    assert payload["running"][0]["session_id"] == "codex:session"
    assert payload["retries"][0]["reason"] == "agent_stalled"


def test_issue_payload_exposes_operator_identifiers() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    payload = issue_payload(_issue(now))

    assert payload == {
        "id": "10001",
        "identifier": "DEMO-1",
        "title": "Add CLI",
        "state": "Ready",
        "url": None,
    }


def _issue(now: datetime) -> Issue:
    return Issue(
        id="10001",
        identifier="DEMO-1",
        title="Add CLI",
        state="Ready",
        created_at=now,
        updated_at=now,
    )
