"""Core dispatch, retry, reconciliation, and cleanup decisions."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from synphony.agent_runner import AgentRunner
from synphony.config import SynphonyConfig
from synphony.models import Issue, RetryEntry, RunAttempt, RuntimeState, normalize_state_name
from synphony.tracker.base import Tracker
from synphony.workspace import WorkspaceManager


class Orchestrator:
    def __init__(
        self,
        *,
        config: SynphonyConfig,
        tracker: Tracker,
        runner: AgentRunner,
        workspace_manager: WorkspaceManager,
        state: RuntimeState | None = None,
    ) -> None:
        self.config = config
        self.tracker = tracker
        self.runner = runner
        self.workspace_manager = workspace_manager
        self.state = state or RuntimeState()

    def claim_dispatchable_issues(self, *, now: datetime) -> list[Issue]:
        candidates = self._candidate_issues_with_due_retries(now=now)
        claimed: list[Issue] = []
        running_or_claimed = set(self.state.running) | self.state.claimed_issue_ids
        per_state_counts = self._running_counts_by_state()

        for issue in sorted(candidates, key=_dispatch_sort_key):
            if issue.id in running_or_claimed:
                continue
            if issue.is_blocked or not self._is_active_state(issue.state):
                continue
            if len(running_or_claimed) >= self.config.agent_max_concurrent_agents:
                break

            normalized_state = normalize_state_name(issue.state)
            state_cap = self._per_state_caps().get(normalized_state)
            if state_cap is not None and per_state_counts.get(normalized_state, 0) >= state_cap:
                continue

            self.state.claimed_issue_ids.add(issue.id)
            running_or_claimed.add(issue.id)
            per_state_counts[normalized_state] = per_state_counts.get(normalized_state, 0) + 1
            claimed.append(issue)

        return claimed

    def reconcile(self, *, now: datetime) -> None:
        if not self.state.running:
            return

        states = self.tracker.fetch_issue_states_by_ids(list(self.state.running))
        for issue_id, live_session in list(self.state.running.items()):
            state = states.get(issue_id, live_session.issue.state)
            if self._is_terminal_state(state):
                self.runner.stop(live_session)
                self.workspace_manager.cleanup_workspace(live_session.workspace)
                self._release(issue_id)
                continue

            if not self._is_active_state(state):
                self.runner.stop(live_session)
                self._release(issue_id)
                continue

            if self._is_stalled(live_session.last_event_at, now=now):
                self.runner.stop(live_session)
                self._schedule_retry(live_session.issue, live_session.attempt.attempt + 1, now=now)
                self._release(issue_id)

    def cleanup_terminal_workspaces(self) -> None:
        for issue in self.tracker.fetch_issues_by_states(self.config.terminal_states):
            workspace = self.workspace_manager.workspace_for_issue(issue)
            if Path(workspace.path).exists():
                self.workspace_manager.cleanup_workspace(workspace)

    def _candidate_issues_with_due_retries(self, *, now: datetime) -> list[Issue]:
        future_retries: list[RetryEntry] = []
        due_retry_issues: list[Issue] = []
        for retry in self.state.retries:
            if retry.next_retry_at <= now:
                due_retry_issues.append(retry.issue)
            else:
                future_retries.append(retry)
        self.state.retries = future_retries

        candidate_by_id = {issue.id: issue for issue in self.tracker.fetch_candidate_issues()}
        for issue in due_retry_issues:
            candidate_by_id[issue.id] = issue
        return list(candidate_by_id.values())

    def _running_counts_by_state(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for live_session in self.state.running.values():
            normalized = live_session.issue.normalized_state
            counts[normalized] = counts.get(normalized, 0) + 1
        return counts

    def _per_state_caps(self) -> dict[str, int]:
        return {
            normalize_state_name(state): cap
            for state, cap in self.config.agent_max_concurrent_agents_by_state.items()
        }

    def _is_active_state(self, state: str) -> bool:
        return normalize_state_name(state) in {
            normalize_state_name(item) for item in self.config.active_states
        }

    def _is_terminal_state(self, state: str) -> bool:
        return normalize_state_name(state) in {
            normalize_state_name(item) for item in self.config.terminal_states
        }

    def _is_stalled(self, last_event_at: datetime, *, now: datetime) -> bool:
        elapsed_ms = (now - last_event_at).total_seconds() * 1000
        return elapsed_ms >= self.config.agent_stall_timeout_ms

    def _schedule_retry(self, issue: Issue, attempt_number: int, *, now: datetime) -> None:
        backoff_ms = min(
            self.config.agent_initial_retry_backoff_ms * (2 ** max(attempt_number - 2, 0)),
            self.config.agent_max_retry_backoff_ms,
        )
        self.state.retries.append(
            RetryEntry(
                issue=issue,
                attempt=_run_attempt(issue, attempt_number),
                next_retry_at=now + timedelta(milliseconds=backoff_ms),
                reason="agent_stalled",
                backoff_ms=backoff_ms,
            )
        )

    def _release(self, issue_id: str) -> None:
        self.state.running.pop(issue_id, None)
        self.state.claimed_issue_ids.discard(issue_id)


def _dispatch_sort_key(issue: Issue) -> tuple[int, datetime, str]:
    priority = issue.priority if issue.priority is not None else 1_000_000
    return priority, issue.created_at, issue.identifier


def _run_attempt(issue: Issue, attempt_number: int) -> RunAttempt:
    return RunAttempt(
        issue_id=issue.id,
        issue_identifier=issue.identifier,
        attempt=attempt_number,
    )
