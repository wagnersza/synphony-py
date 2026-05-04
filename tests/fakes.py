"""Reusable test doubles for synphony unit tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from synphony.agents.base import AgentTurnInput, AgentTurnRequest, AgentTurnResult
from synphony.errors import AgentTimeoutError
from synphony.models import AgentEvent

FakeTurnOutcome = Literal["success", "failure", "stall"]


@dataclass(frozen=True, slots=True)
class FakeAgentTurn:
    outcome: FakeTurnOutcome
    message: str | None = None
    error_code: str | None = None
    timeout_ms: int | None = None

    @classmethod
    def success(cls, *, message: str = "turn completed") -> FakeAgentTurn:
        return cls(outcome="success", message=message)

    @classmethod
    def failure(cls, *, message: str, error_code: str) -> FakeAgentTurn:
        return cls(outcome="failure", message=message, error_code=error_code)

    @classmethod
    def stall(cls, *, timeout_ms: int) -> FakeAgentTurn:
        return cls(outcome="stall", timeout_ms=timeout_ms)


class FakeAgentBackend:
    """Deterministic backend for orchestrator and runner tests."""

    def __init__(
        self,
        *,
        provider: str = "codex",
        script: tuple[FakeAgentTurn, ...] | None = None,
        results: list[AgentTurnResult] | None = None,
        after_turn: Callable[[AgentTurnRequest], None] | None = None,
    ) -> None:
        self.provider = provider
        self._script = script or (FakeAgentTurn.success(),)
        self._script_index = 0
        self._session_count = 0
        self._turn_count = 0
        self._results = list(results) if results is not None else None
        self.after_turn = after_turn
        self.requests: list[AgentTurnRequest] = []
        self._stopped_sessions: list[tuple[str, Path | None]] = []

    @property
    def stopped_sessions(self) -> tuple[str, ...] | list[tuple[str, Path]]:
        if all(cwd is None for _, cwd in self._stopped_sessions):
            return tuple(session_id for session_id, _ in self._stopped_sessions)
        return [(session_id, cwd) for session_id, cwd in self._stopped_sessions if cwd is not None]

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        self._session_count += 1
        session_id = f"{self.provider}:fake-session-{self._session_count}"
        return self._run_scripted_turn(turn, session_id=session_id, include_session_started=True)

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        if turn.session_id is None:
            msg = "fake continuation requires an existing session_id"
            raise ValueError(msg)
        return self._run_scripted_turn(
            turn,
            session_id=turn.session_id,
            include_session_started=False,
        )

    def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        self.requests.append(request)
        if self._results is not None:
            result = (
                self._results.pop(0)
                if self._results
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

        turn = AgentTurnInput(
            provider=request.provider,
            prompt=request.prompt,
            issue=request.issue,
            workspace=request.workspace,
            session_id=request.session_id,
            on_event=request.on_event,
        )
        if request.session_id is None:
            return self.start_session(turn)
        return self.continue_session(turn)

    def stop_session(
        self,
        session_id: str,
        *,
        cwd: Path | None = None,
        timeout: object = None,
    ) -> None:
        self._stopped_sessions.append((session_id, cwd))

    def _run_scripted_turn(
        self,
        turn: AgentTurnInput,
        *,
        session_id: str,
        include_session_started: bool,
    ) -> AgentTurnResult:
        scripted = self._next_scripted_turn()
        if scripted.outcome == "stall":
            timeout_ms = scripted.timeout_ms or _timeout_to_ms(turn)
            raise AgentTimeoutError(provider=self.provider, timeout_ms=timeout_ms)

        self._turn_count += 1
        turn_id = f"fake-turn-{self._turn_count}"
        events: list[AgentEvent] = []

        if include_session_started:
            events.append(self._event(session_id=session_id, kind="session.started"))
        events.append(self._event(session_id=session_id, kind="turn.started", turn_id=turn_id))

        if scripted.outcome == "failure":
            events.append(
                self._event(
                    session_id=session_id,
                    kind="turn.failed",
                    turn_id=turn_id,
                    message=scripted.message,
                    raw={"error_code": scripted.error_code},
                )
            )
        else:
            events.append(
                self._event(
                    session_id=session_id,
                    kind="turn.completed",
                    turn_id=turn_id,
                    message=scripted.message,
                )
            )

        for event in events:
            if turn.on_event is not None:
                turn.on_event(event)

        return AgentTurnResult(
            session_id=session_id,
            turn_id=turn_id,
            events=tuple(events),
            completed=scripted.outcome != "failure",
        )

    def _next_scripted_turn(self) -> FakeAgentTurn:
        if self._script_index >= len(self._script):
            return FakeAgentTurn.success()
        turn = self._script[self._script_index]
        self._script_index += 1
        return turn

    def _event(
        self,
        *,
        session_id: str,
        kind: str,
        turn_id: str | None = None,
        message: str | None = None,
        raw: dict[str, object] | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            provider=self.provider,
            session_id=session_id,
            kind=kind,
            occurred_at=datetime.now(UTC),
            turn_id=turn_id,
            message=message,
            raw=raw or {},
        )


def _timeout_to_ms(turn: AgentTurnInput) -> int:
    if turn.timeout is None:
        return 0
    return int(turn.timeout.total_seconds() * 1000)
