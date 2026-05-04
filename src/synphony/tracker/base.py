"""Tracker protocol used by the orchestrator boundary."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Protocol

from synphony.models import Issue


class Tracker(Protocol):
    """Provider-neutral issue tracker operations required by orchestration."""

    def fetch_candidate_issues(self) -> Sequence[Issue]:
        """Fetch issues currently eligible for dispatch."""

    def fetch_issues_by_states(self, state_names: Collection[str]) -> Sequence[Issue]:
        """Fetch issues whose tracker state matches any provided state name."""

    def fetch_issue_states_by_ids(self, issue_ids: Collection[str]) -> dict[str, str]:
        """Fetch current tracker state names keyed by issue id."""
