"""Provider-agnostic agent backend boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from synphony.models import AgentEvent, Issue, RunAttempt, Workspace

AgentEventCallback = Callable[[AgentEvent], None]


@dataclass(frozen=True, slots=True)
class AgentTurnInput:
    """Inputs shared by first and continuation turns for any provider."""

    provider: str
    prompt: str
    issue: Issue
    workspace: Workspace
    session_id: str | None = None
    turn_id: str | None = None
    timeout: timedelta | None = None
    on_event: AgentEventCallback | None = None

    def with_event_callback(self, callback: AgentEventCallback) -> AgentTurnInput:
        return AgentTurnInput(
            provider=self.provider,
            prompt=self.prompt,
            issue=self.issue,
            workspace=self.workspace,
            session_id=self.session_id,
            turn_id=self.turn_id,
            timeout=self.timeout,
            on_event=callback,
        )

    def with_prompt(self, prompt: str) -> AgentTurnInput:
        return AgentTurnInput(
            provider=self.provider,
            prompt=prompt,
            issue=self.issue,
            workspace=self.workspace,
            session_id=self.session_id,
            turn_id=self.turn_id,
            timeout=self.timeout,
            on_event=self.on_event,
        )


@dataclass(frozen=True, slots=True)
class AgentTurnRequest:
    provider: str
    cwd: Path
    issue: Issue
    workspace: Workspace
    attempt: RunAttempt
    prompt: str
    turn_number: int
    max_turns: int
    session_id: str | None
    on_event: Callable[[AgentEvent], None]
    turn_timeout_ms: int | None = None
    stall_timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    """Normalized result from a provider turn."""

    session_id: str
    events: tuple[AgentEvent, ...] = ()
    turn_id: str | None = None
    completed: bool = True
    exit_code: int = 0
    message: str | None = None
    raw_events: tuple[dict[str, object], ...] = ()

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class AgentBackend(Protocol):
    """Backend contract consumed by the provider-agnostic runner."""

    @property
    def provider(self) -> str:
        """Stable provider id used for registry dispatch."""

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        """Start a provider session and run the first turn."""

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        """Run a continuation turn against an existing session."""

    def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        """Run one provider turn in the issue workspace."""
        ...

    def stop_session(
        self,
        session_id: str,
        *,
        cwd: Path | None = None,
        timeout: timedelta | None = None,
    ) -> None:
        """Best-effort stop for a live provider session."""
        ...
