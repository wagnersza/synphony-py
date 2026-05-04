"""Shared contract for coding-agent backends."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from synphony.errors import AgentNotFoundError
from synphony.models import AgentEvent

AgentEventCallback = Callable[[AgentEvent], None]


@dataclass(frozen=True, slots=True)
class AgentTurnRequest:
    prompt: str
    cwd: Path
    session_id: str | None = None
    turn_timeout_ms: int | None = None
    stall_timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    provider: str
    session_id: str
    exit_code: int
    message: str | None = None
    raw_events: tuple[dict[str, object], ...] = ()


class AgentBackend(Protocol):
    provider: str

    def run_first_turn(
        self,
        request: AgentTurnRequest,
        on_event: AgentEventCallback | None = None,
    ) -> AgentRunResult:
        """Run the first turn for a new agent session."""

    def run_continuation_turn(
        self,
        request: AgentTurnRequest,
        on_event: AgentEventCallback | None = None,
    ) -> AgentRunResult:
        """Run a continuation turn for an existing agent session."""

    def stop(self, session_id: str) -> bool:
        """Stop a running session if the backend keeps one alive."""


@dataclass(slots=True)
class AgentBackendRegistry:
    _factories: dict[str, Callable[[], AgentBackend | object]] = field(default_factory=dict)

    def register(self, provider: str, factory: Callable[[], AgentBackend | object]) -> None:
        self._factories[provider] = factory

    def create(self, provider: str) -> AgentBackend | object:
        try:
            return self._factories[provider]()
        except KeyError as exc:
            raise AgentNotFoundError(
                f"agent provider is not registered: {provider}",
                details={"provider": provider},
            ) from exc
