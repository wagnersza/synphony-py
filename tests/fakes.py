from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from synphony.agents.base import AgentBackend, AgentTurnRequest, AgentTurnResult
from synphony.models import AgentEvent


class FakeAgentBackend(AgentBackend):
    def __init__(
        self,
        *,
        provider: str = "codex",
        results: list[AgentTurnResult] | None = None,
        after_turn: Callable[[AgentTurnRequest], None] | None = None,
    ) -> None:
        self.provider = provider
        self.results = list(results or [AgentTurnResult(session_id=f"{provider}:session")])
        self.after_turn = after_turn
        self.requests: list[AgentTurnRequest] = []
        self.stopped_sessions: list[tuple[str, Path]] = []

    def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        result = (
            self.results.pop(0)
            if self.results
            else AgentTurnResult(session_id=f"{self.provider}:done")
        )
        request.on_event(
            AgentEvent(
                provider=self.provider,
                session_id=result.session_id,
                kind="turn.completed" if result.completed else "turn.awaiting_continuation",
                occurred_at=datetime.now(UTC),
                turn_id=f"turn-{request.turn_number}",
            )
        )
        if self.after_turn is not None:
            self.after_turn(request)
        return result

    def stop_session(self, *, session_id: str, cwd: Path) -> None:
        self.stopped_sessions.append((session_id, cwd))
