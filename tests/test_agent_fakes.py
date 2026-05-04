from datetime import timedelta

import pytest
from fakes import FakeAgentBackend, FakeAgentTurn

from synphony.agents.base import AgentTurnInput
from synphony.errors import AgentTimeoutError
from synphony.models import AgentEvent, Issue, Workspace


def _turn_input(make_issue: Issue, *, session_id: str | None = None) -> AgentTurnInput:
    return AgentTurnInput(
        provider="codex",
        prompt="Work on {{ issue.identifier }}",
        issue=make_issue,
        workspace=Workspace(path="/tmp/work/demo-1", key="demo-1", created_now=True),
        session_id=session_id,
        timeout=timedelta(seconds=30),
    )


def test_fake_backend_emits_normalized_success_events(make_issue: Issue) -> None:
    seen: list[AgentEvent] = []
    backend = FakeAgentBackend(provider="codex")

    result = backend.start_session(_turn_input(make_issue).with_event_callback(seen.append))

    assert result.session_id == "codex:fake-session-1"
    assert [event.kind for event in result.events] == [
        "session.started",
        "turn.started",
        "turn.completed",
    ]
    assert seen == list(result.events)
    assert {event.provider for event in result.events} == {"codex"}


def test_fake_backend_uses_scripted_failure(make_issue: Issue) -> None:
    backend = FakeAgentBackend(
        provider="claude",
        script=(FakeAgentTurn.failure(message="tool failed", error_code="agent_protocol_error"),),
    )

    result = backend.start_session(_turn_input(make_issue))

    assert result.session_id == "claude:fake-session-1"
    assert [event.kind for event in result.events] == [
        "session.started",
        "turn.started",
        "turn.failed",
    ]
    assert result.events[-1].message == "tool failed"
    assert result.events[-1].raw == {"error_code": "agent_protocol_error"}


def test_fake_backend_can_simulate_stall_timeout(make_issue: Issue) -> None:
    backend = FakeAgentBackend(
        provider="codex",
        script=(FakeAgentTurn.stall(timeout_ms=250),),
    )

    with pytest.raises(AgentTimeoutError) as exc_info:
        backend.start_session(_turn_input(make_issue))

    assert exc_info.value.details == {"provider": "codex", "timeout_ms": 250}


def test_fake_backend_continues_existing_session(make_issue: Issue) -> None:
    backend = FakeAgentBackend(provider="codex")
    first = backend.start_session(_turn_input(make_issue))

    continuation = backend.continue_session(
        _turn_input(make_issue, session_id=first.session_id).with_prompt("Continue")
    )

    assert continuation.session_id == first.session_id
    assert continuation.turn_id == "fake-turn-2"
    assert continuation.events[0].session_id == first.session_id


def test_fake_backend_stop_records_session(make_issue: Issue) -> None:
    backend = FakeAgentBackend(provider="codex")
    result = backend.start_session(_turn_input(make_issue))

    backend.stop_session(result.session_id)

    assert backend.stopped_sessions == (result.session_id,)
