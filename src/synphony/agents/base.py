"""Provider-agnostic agent backend boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from synphony.models import AgentEvent, Issue, RunAttempt, Workspace


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


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    session_id: str
    completed: bool = True


class AgentBackend(Protocol):
    provider: str

    def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        """Run one provider turn in the issue workspace."""
        ...

    def stop_session(self, *, session_id: str, cwd: Path) -> None:
        """Best-effort stop for a live provider session."""
        ...
