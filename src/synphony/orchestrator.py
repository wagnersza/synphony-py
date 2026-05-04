"""Core orchestration scheduler."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from synphony.models import (
    Issue,
    LiveSession,
    RetryEntry,
    RunAttempt,
    RuntimeState,
    normalize_state_name,
)
from synphony.tracker.base import Tracker

RunStarter = Callable[[Issue, RunAttempt], LiveSession]
SessionStopper = Callable[[LiveSession], None]
WorkspaceCleaner = Callable[[LiveSession], bool]


@dataclass(frozen=True, slots=True)
class OrchestratorConfig:
    active_state_names: tuple[str, ...]
    terminal_state_names: tuple[str, ...] = ()
    max_concurrent_agents: int = 1
    max_concurrent_agents_by_state: Mapping[str, int] = field(default_factory=dict)
    stall_timeout_s: float | None = None
    retry_base_backoff_ms: int = 1000
    max_retry_backoff_ms: int = 60_000

    def __post_init__(self) -> None:
        if self.max_concurrent_agents < 1:
            msg = "max_concurrent_agents must be at least 1"
            raise ValueError(msg)
        if self.stall_timeout_s is not None and self.stall_timeout_s <= 0:
            msg = "stall_timeout_s must be greater than 0"
            raise ValueError(msg)
        if self.retry_base_backoff_ms < 1:
            msg = "retry_base_backoff_ms must be at least 1"
            raise ValueError(msg)
        if self.max_retry_backoff_ms < self.retry_base_backoff_ms:
            msg = "max_retry_backoff_ms must be greater than or equal to retry_base_backoff_ms"
            raise ValueError(msg)
        for state_name, cap in self.max_concurrent_agents_by_state.items():
            if cap < 1:
                msg = f"max_concurrent_agents_by_state[{state_name!r}] must be at least 1"
                raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    started: tuple[LiveSession, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    stopped: tuple[LiveSession, ...]
    cleaned: tuple[LiveSession, ...]
    retries: tuple[RetryEntry, ...]


class Orchestrator:
    """Dispatch eligible tracker issues while maintaining runtime state."""

    def __init__(
        self,
        *,
        tracker: Tracker,
        config: OrchestratorConfig,
        run_starter: RunStarter,
        session_stopper: SessionStopper | None = None,
        workspace_cleaner: WorkspaceCleaner | None = None,
        state: RuntimeState | None = None,
    ) -> None:
        self._tracker = tracker
        self._config = config
        self._run_starter = run_starter
        self._session_stopper = session_stopper or (lambda session: None)
        self._workspace_cleaner = workspace_cleaner or (lambda session: False)
        self.state = state or RuntimeState()
        self._active_states = {
            normalize_state_name(state_name) for state_name in config.active_state_names
        }
        self._terminal_states = {
            normalize_state_name(state_name) for state_name in config.terminal_state_names
        }
        self._state_caps = {
            normalize_state_name(state_name): cap
            for state_name, cap in config.max_concurrent_agents_by_state.items()
        }

    def dispatch_once(self) -> DispatchResult:
        """Fetch candidates and start as many as current capacity permits."""
        started: list[LiveSession] = []

        for issue in sorted(self._tracker.fetch_candidate_issues(), key=_candidate_sort_key):
            if not self._can_dispatch(issue, started):
                continue

            attempt = RunAttempt(
                issue_id=issue.id,
                issue_identifier=issue.identifier,
                attempt=1,
            )
            self.state.claimed_issue_ids.add(issue.id)
            try:
                live_session = self._run_starter(issue, attempt)
            finally:
                self.state.claimed_issue_ids.discard(issue.id)

            self.state.running[issue.id] = live_session
            started.append(live_session)

        return DispatchResult(started=tuple(started))

    def reconcile_once(self, *, now: datetime) -> ReconciliationResult:
        """Refresh running issues and stop sessions that should no longer run."""
        if not self.state.running:
            return ReconciliationResult(stopped=(), cleaned=(), retries=())

        current_states = self._tracker.fetch_issue_states_by_ids(tuple(self.state.running))
        stopped: list[LiveSession] = []
        cleaned: list[LiveSession] = []
        retries: list[RetryEntry] = []

        for issue_id, session in list(self.state.running.items()):
            current_state = current_states.get(issue_id)
            if self._is_terminal_state(current_state):
                self._stop_running_session(issue_id, session)
                stopped.append(session)
                if self._workspace_cleaner(session):
                    cleaned.append(session)
                continue

            if not self._is_active_state(current_state):
                self._stop_running_session(issue_id, session)
                stopped.append(session)
                continue

            if self._is_stalled(session, now):
                self._stop_running_session(issue_id, session)
                stopped.append(session)
                retry = self._schedule_retry(session, now=now, reason="stalled")
                retries.append(retry)

        return ReconciliationResult(
            stopped=tuple(stopped),
            cleaned=tuple(cleaned),
            retries=tuple(retries),
        )

    def _can_dispatch(self, issue: Issue, started: list[LiveSession]) -> bool:
        if issue.is_blocked:
            return False
        if issue.id in self.state.running:
            return False
        if issue.id in self.state.claimed_issue_ids:
            return False
        if issue.id in self._retry_issue_ids:
            return False
        if self._global_in_flight_count(started) >= self._config.max_concurrent_agents:
            return False

        state_cap = self._state_caps.get(issue.normalized_state)
        if state_cap is None:
            return True

        return self._state_in_flight_count(issue.normalized_state, started) < state_cap

    @property
    def _retry_issue_ids(self) -> set[str]:
        return {entry.issue.id for entry in self.state.retries}

    def _stop_running_session(self, issue_id: str, session: LiveSession) -> None:
        self._session_stopper(session)
        self.state.running.pop(issue_id, None)

    def _schedule_retry(self, session: LiveSession, *, now: datetime, reason: str) -> RetryEntry:
        next_attempt_number = session.attempt.attempt + 1
        backoff_ms = min(
            self._config.retry_base_backoff_ms * (2 ** max(0, next_attempt_number - 2)),
            self._config.max_retry_backoff_ms,
        )
        retry = RetryEntry(
            issue=session.issue,
            attempt=RunAttempt(
                issue_id=session.issue.id,
                issue_identifier=session.issue.identifier,
                attempt=next_attempt_number,
            ),
            next_retry_at=now + timedelta(milliseconds=backoff_ms),
            reason=reason,
            backoff_ms=backoff_ms,
        )
        self.state.retries.append(retry)
        return retry

    def _is_terminal_state(self, state: str | None) -> bool:
        if state is None:
            return False
        return normalize_state_name(state) in self._terminal_states

    def _is_active_state(self, state: str | None) -> bool:
        if state is None:
            return False
        return normalize_state_name(state) in self._active_states

    def _is_stalled(self, session: LiveSession, now: datetime) -> bool:
        if self._config.stall_timeout_s is None:
            return False
        return now - session.last_event_at > timedelta(seconds=self._config.stall_timeout_s)

    def _global_in_flight_count(self, started: list[LiveSession]) -> int:
        _ = started
        return len(self.state.running) + len(self.state.claimed_issue_ids)

    def _state_in_flight_count(self, normalized_state: str, started: list[LiveSession]) -> int:
        running_count = sum(
            1
            for session in self.state.running.values()
            if session.issue.normalized_state == normalized_state
        )
        _ = started
        return running_count


def _candidate_sort_key(issue: Issue) -> tuple[int, int, datetime, str]:
    has_priority = 0 if issue.priority is not None else 1
    priority = issue.priority if issue.priority is not None else 0
    return has_priority, priority, issue.created_at, issue.identifier
