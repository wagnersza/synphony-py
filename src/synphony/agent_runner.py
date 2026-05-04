"""Provider-neutral agent runner loop."""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

from synphony.agents.base import AgentBackend, AgentEventCallback, AgentTurnInput, AgentTurnResult
from synphony.models import AgentEvent, Issue, RunAttempt, Workspace, normalize_state_name
from synphony.prompt import render_prompt
from synphony.workspace import WorkspaceManager

IssueStateFetcher = Callable[[Collection[str]], Mapping[str, str]]


class StopReason(Enum):
    """Why a runner returned control to the orchestrator."""

    INACTIVE = "inactive"
    MAX_TURNS = "max_turns"
    AGENT_FAILED = "agent_failed"


@dataclass(frozen=True, slots=True)
class AgentRunConfig:
    active_state_names: Collection[str]
    max_turns: int = 20
    turn_timeout_s: float | None = None

    def __post_init__(self) -> None:
        if self.max_turns < 1:
            msg = "max_turns must be at least 1"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    issue: Issue
    workspace: Workspace
    session_id: str
    turns_completed: int
    stop_reason: StopReason
    events: tuple[AgentEvent, ...]
    last_turn_id: str | None = None


class AgentRunner:
    """Run one issue through a provider backend in a prepared workspace."""

    def __init__(
        self,
        *,
        backend: AgentBackend,
        workspace_manager: WorkspaceManager,
        prompt_template: str,
        config: AgentRunConfig,
        issue_state_fetcher: IssueStateFetcher,
    ) -> None:
        self._backend = backend
        self._workspace_manager = workspace_manager
        self._prompt_template = prompt_template
        self._config = config
        self._issue_state_fetcher = issue_state_fetcher
        self._active_states = {
            normalize_state_name(state_name) for state_name in config.active_state_names
        }

    def run(
        self,
        issue: Issue,
        attempt: RunAttempt,
        *,
        on_event: AgentEventCallback | None = None,
    ) -> AgentRunResult:
        workspace = self._workspace_manager.prepare(issue.identifier)
        events: list[AgentEvent] = []
        session_id: str | None = None
        last_turn_id: str | None = None
        turns_completed = 0
        stop_reason = StopReason.MAX_TURNS

        def record_event(event: AgentEvent) -> None:
            events.append(event)
            if on_event is not None:
                on_event(event)

        try:
            self._workspace_manager.run_before_run(workspace)

            for turn_number in range(1, self._config.max_turns + 1):
                turn = self._build_turn(
                    issue=issue,
                    attempt=attempt,
                    workspace=workspace,
                    turn_number=turn_number,
                    session_id=session_id,
                    last_turn_id=last_turn_id,
                    on_event=record_event,
                )
                event_count_before_turn = len(events)
                result = self._run_backend_turn(turn)
                if len(events) == event_count_before_turn:
                    self._record_uncalled_events(result, record_event)

                session_id = result.session_id
                last_turn_id = result.turn_id
                turns_completed += 1

                if _turn_failed(result):
                    stop_reason = StopReason.AGENT_FAILED
                    break

                if not self._issue_still_active(issue.id, issue.state):
                    stop_reason = StopReason.INACTIVE
                    break
            else:
                stop_reason = StopReason.MAX_TURNS

            if turns_completed >= self._config.max_turns and stop_reason is not StopReason.INACTIVE:
                stop_reason = StopReason.MAX_TURNS

            if session_id is None:
                msg = "agent backend did not return a session id"
                raise RuntimeError(msg)

            return AgentRunResult(
                issue=issue,
                workspace=workspace,
                session_id=session_id,
                turns_completed=turns_completed,
                stop_reason=stop_reason,
                events=tuple(events),
                last_turn_id=last_turn_id,
            )
        finally:
            if session_id is not None:
                self._backend.stop_session(session_id)
            self._workspace_manager.run_after_run(workspace)

    def _build_turn(
        self,
        *,
        issue: Issue,
        attempt: RunAttempt,
        workspace: Workspace,
        turn_number: int,
        session_id: str | None,
        last_turn_id: str | None,
        on_event: AgentEventCallback,
    ) -> AgentTurnInput:
        prompt = (
            render_prompt(self._prompt_template, issue=issue, attempt=attempt)
            if turn_number == 1
            else _continuation_prompt(turn_number=turn_number, max_turns=self._config.max_turns)
        )
        timeout = (
            timedelta(seconds=self._config.turn_timeout_s)
            if self._config.turn_timeout_s is not None
            else None
        )
        return AgentTurnInput(
            provider=self._backend.provider,
            prompt=prompt,
            issue=issue,
            workspace=workspace,
            session_id=session_id,
            turn_id=last_turn_id,
            timeout=timeout,
            on_event=on_event,
        )

    def _run_backend_turn(self, turn: AgentTurnInput) -> AgentTurnResult:
        if turn.session_id is None:
            return self._backend.start_session(turn)
        return self._backend.continue_session(turn)

    def _record_uncalled_events(
        self,
        result: AgentTurnResult,
        record_event: AgentEventCallback,
    ) -> None:
        for event in result.events:
            record_event(event)

    def _issue_still_active(self, issue_id: str, fallback_state: str) -> bool:
        states = self._issue_state_fetcher([issue_id])
        state = states.get(issue_id, fallback_state)
        return normalize_state_name(state) in self._active_states


def _turn_failed(result: AgentTurnResult) -> bool:
    return any(event.kind == "turn.failed" for event in result.events)


def _continuation_prompt(*, turn_number: int, max_turns: int) -> str:
    return f"""Continuation guidance:

- The previous agent turn completed normally, but the Jira issue is still in an active state.
- This is continuation turn #{turn_number} of {max_turns} for the current agent run.
- Resume from the current workspace and prior session context instead of restarting from scratch.
- The original task instructions are already present in this session.
- Do not restate them before acting.
- Focus on the remaining ticket work and stop only when the issue is complete or truly blocked.
"""
