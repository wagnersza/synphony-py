"""Provider-agnostic agent backend protocol."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from synphony.models import AgentEvent, Issue, Workspace

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
class AgentTurnResult:
    """Normalized result from a provider turn."""

    session_id: str
    events: tuple[AgentEvent, ...]
    turn_id: str | None = None

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class AgentBackend(Protocol):
    """Backend contract consumed by the future provider-agnostic runner."""

    @property
    def provider(self) -> str:
        """Stable provider id used for registry dispatch."""

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        """Start a provider session and run the first turn."""

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        """Run a continuation turn against an existing session."""

    def stop_session(self, session_id: str, *, timeout: timedelta | None = None) -> None:
        """Stop or interrupt a provider session if the backend supports it."""
