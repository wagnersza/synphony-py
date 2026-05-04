"""Deterministic in-memory tracker for unit tests."""

from __future__ import annotations

from dataclasses import replace

from synphony.models import Issue, normalize_state_name
from synphony.tracker.base import Tracker


class MemoryTracker(Tracker):
    def __init__(self, issues: list[Issue] | tuple[Issue, ...] = ()) -> None:
        self._issues: dict[str, Issue] = {issue.id: issue for issue in issues}

    def fetch_candidate_issues(self) -> list[Issue]:
        return list(self._issues.values())

    def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
        normalized = {normalize_state_name(state) for state in state_names}
        return [issue for issue in self._issues.values() if issue.normalized_state in normalized]

    def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> dict[str, str]:
        return {
            issue_id: self._issues[issue_id].state
            for issue_id in issue_ids
            if issue_id in self._issues
        }

    def set_issue_state(self, issue_id: str, state: str) -> None:
        self._issues[issue_id] = replace(self._issues[issue_id], state=state)

    def upsert_issue(self, issue: Issue) -> None:
        self._issues[issue.id] = issue
