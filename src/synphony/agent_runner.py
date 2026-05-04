"""Shared provider-agnostic issue runner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from synphony.agents.base import AgentBackend, AgentTurnRequest
from synphony.config import SynphonyConfig
from synphony.models import (
    AgentEvent,
    Issue,
    LiveSession,
    RunAttempt,
    Workspace,
    normalize_state_name,
)
from synphony.prompt import build_continuation_prompt, build_first_prompt
from synphony.tracker.base import Tracker
from synphony.workspace import WorkspaceManager


@dataclass(frozen=True, slots=True)
class AgentRunOutcome:
    issue: Issue
    workspace: Workspace
    attempt: RunAttempt
    provider: str
    session_id: str
    turns_completed: int
    stop_reason: str
    started_at: datetime
    last_event_at: datetime

    def live_session(self) -> LiveSession:
        return LiveSession(
            issue=self.issue,
            workspace=self.workspace,
            attempt=self.attempt,
            provider=self.provider,
            session_id=self.session_id,
            started_at=self.started_at,
            last_event_at=self.last_event_at,
        )


class AgentRunner:
    def __init__(
        self,
        *,
        config: SynphonyConfig,
        workflow_prompt_template: str,
        tracker: Tracker,
        workspace_manager: WorkspaceManager,
        backend: AgentBackend,
    ) -> None:
        self._config = config
        self._workflow_prompt_template = workflow_prompt_template
        self._tracker = tracker
        self._workspace_manager = workspace_manager
        self._backend = backend

    @property
    def backend(self) -> AgentBackend:
        return self._backend

    def run(
        self,
        issue: Issue,
        *,
        attempt_number: int,
        on_event: Callable[[AgentEvent], None],
    ) -> AgentRunOutcome:
        attempt = RunAttempt(
            issue_id=issue.id,
            issue_identifier=issue.identifier,
            attempt=attempt_number,
        )
        workspace = self._workspace_manager.prepare_workspace(issue)
        if workspace.created_now:
            self._workspace_manager.run_hook("after_create", workspace)

        started_at = datetime.now(UTC)
        last_event_at = started_at
        session_id: str | None = None
        turns_completed = 0

        for turn_number in range(1, self._config.agent_max_turns + 1):
            prompt = (
                build_first_prompt(self._workflow_prompt_template, issue=issue, attempt=attempt)
                if turn_number == 1
                else build_continuation_prompt(issue=issue, attempt=attempt)
            )
            self._workspace_manager.run_hook("before_run", workspace)

            def capture_event(event: AgentEvent) -> None:
                nonlocal last_event_at
                last_event_at = event.occurred_at
                on_event(event)

            result = self._backend.run_turn(
                AgentTurnRequest(
                    provider=self._config.agent_provider,
                    cwd=Path(workspace.path),
                    issue=issue,
                    workspace=workspace,
                    attempt=attempt,
                    prompt=prompt,
                    turn_number=turn_number,
                    max_turns=self._config.agent_max_turns,
                    session_id=session_id,
                    on_event=capture_event,
                )
            )
            turns_completed = turn_number
            session_id = result.session_id
            self._workspace_manager.run_hook("after_run", workspace)

            if result.completed:
                return AgentRunOutcome(
                    issue=issue,
                    workspace=workspace,
                    attempt=attempt,
                    provider=self._config.agent_provider,
                    session_id=session_id,
                    turns_completed=turns_completed,
                    stop_reason="completed",
                    started_at=started_at,
                    last_event_at=last_event_at,
                )
            if turn_number == self._config.agent_max_turns:
                break
            if not self._issue_still_active(issue):
                return AgentRunOutcome(
                    issue=issue,
                    workspace=workspace,
                    attempt=attempt,
                    provider=self._config.agent_provider,
                    session_id=session_id,
                    turns_completed=turns_completed,
                    stop_reason="issue_inactive",
                    started_at=started_at,
                    last_event_at=last_event_at,
                )

        return AgentRunOutcome(
            issue=issue,
            workspace=workspace,
            attempt=attempt,
            provider=self._config.agent_provider,
            session_id=session_id or f"{self._config.agent_provider}:{issue.id}",
            turns_completed=turns_completed,
            stop_reason="max_turns",
            started_at=started_at,
            last_event_at=last_event_at,
        )

    def stop(self, live_session: LiveSession) -> None:
        self._backend.stop_session(
            session_id=live_session.session_id,
            cwd=Path(live_session.workspace.path),
        )

    def _issue_still_active(self, issue: Issue) -> bool:
        states = self._tracker.fetch_issue_states_by_ids([issue.id])
        state = states.get(issue.id, issue.state)
        active_states = {normalize_state_name(item) for item in self._config.active_states}
        return normalize_state_name(state) in active_states
