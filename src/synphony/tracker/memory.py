"""Deterministic in-memory tracker for tests and local orchestration."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import replace
from datetime import datetime

from synphony.models import Issue, normalize_state_name
from synphony.tracker.base import Tracker


class MemoryTracker(Tracker):
    """A small tracker fake that preserves issue shape without external I/O."""

    def __init__(
        self,
        issues: Iterable[Issue] = (),
        *,
        active_state_names: Collection[str] | None = None,
        terminal_state_names: Collection[str] = (),
    ) -> None:
        self._issues: dict[str, Issue] = {issue.id: issue for issue in issues}
        self._active_states = (
            _normalize_states(active_state_names) if active_state_names is not None else None
        )
        self._terminal_states = _normalize_states(terminal_state_names)

    @property
    def terminal_state_names(self) -> set[str]:
        return set(self._terminal_states)

    def add_issue(self, issue: Issue) -> None:
        self._issues[issue.id] = issue

    def fetch_candidate_issues(self) -> list[Issue]:
        issues = list(self._issues.values())
        if self._active_states is not None:
            issues = [issue for issue in issues if issue.normalized_state in self._active_states]
        return sorted(issues, key=_candidate_sort_key)

    def fetch_issues_by_states(self, state_names: Collection[str]) -> list[Issue]:
        states = _normalize_states(state_names)
        return [issue for issue in self._issues.values() if issue.normalized_state in states]

    def fetch_issue_states_by_ids(self, issue_ids: Collection[str]) -> dict[str, str]:
        return {
            issue_id: self._issues[issue_id].state
            for issue_id in issue_ids
            if issue_id in self._issues
        }

    def set_issue_state(self, issue_id: str, state: str) -> None:
        self._issues[issue_id] = replace(self._issues[issue_id], state=state)

    def upsert_issue(self, issue: Issue) -> None:
        self._issues[issue.id] = issue


def _normalize_states(state_names: Collection[str]) -> set[str]:
    return {normalize_state_name(state_name) for state_name in state_names}


def _candidate_sort_key(issue: Issue) -> tuple[int, int, datetime, str]:
    has_priority = 0 if issue.priority is not None else 1
    priority = issue.priority if issue.priority is not None else 0
    return has_priority, priority, issue.created_at, issue.identifier
