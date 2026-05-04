"""Issue tracker protocol used by the orchestrator."""

from __future__ import annotations

from typing import Protocol

from synphony.models import Issue


class Tracker(Protocol):
    def fetch_candidate_issues(self) -> list[Issue]:
        """Fetch issues that may be eligible for dispatch."""
        ...

    def fetch_issues_by_states(self, state_names: list[str]) -> list[Issue]:
        """Fetch issues currently in any of the provided tracker states."""
        ...

    def fetch_issue_states_by_ids(self, issue_ids: list[str]) -> dict[str, str]:
        """Fetch current state names for the provided issue ids."""
        ...
