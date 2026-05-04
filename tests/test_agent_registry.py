from datetime import timedelta

import pytest

from synphony.agents.base import AgentTurnInput, AgentTurnResult
from synphony.agents.codex import CodexBackend
from synphony.agents.registry import AgentRegistry, create_default_registry
from synphony.config import SynphonyConfig
from synphony.errors import AgentNotFoundError
from synphony.models import AgentEvent, Issue, Workspace


class _Backend:
    provider = "codex"

    def __init__(self) -> None:
        self.stopped: list[str] = []

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        return AgentTurnResult(session_id=f"{self.provider}:session", events=())

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        return AgentTurnResult(session_id=turn.session_id or "missing", events=())

    def stop_session(self, session_id: str, *, timeout: timedelta | None = None) -> None:
        self.stopped.append(session_id)


def test_registry_dispatches_supported_provider(make_issue: Issue) -> None:
    backend = _Backend()
    registry = AgentRegistry()
    registry.register(backend)

    resolved = registry.get("codex")
    result = resolved.start_session(
        AgentTurnInput(
            provider="codex",
            prompt="Implement the ticket",
            issue=make_issue,
            workspace=Workspace(path="/tmp/work/demo-1", key="demo-1", created_now=True),
            timeout=timedelta(seconds=30),
            on_event=lambda _event: None,
        )
    )

    assert resolved is backend
    assert result.session_id == "codex:session"


def test_registry_rejects_duplicate_provider() -> None:
    registry = AgentRegistry()
    registry.register(_Backend())

    with pytest.raises(ValueError, match="codex"):
        registry.register(_Backend())


def test_registry_reports_unsupported_provider() -> None:
    registry = AgentRegistry()

    with pytest.raises(AgentNotFoundError) as exc_info:
        registry.get("opencode")

    assert exc_info.value.code == "agent_not_found"
    assert exc_info.value.details == {"provider": "opencode"}


def test_default_registry_reserves_v1_provider_keys() -> None:
    registry = create_default_registry()

    assert sorted(registry.provider_ids) == ["claude", "codex"]
    assert isinstance(registry.get("codex"), CodexBackend)


def test_default_registry_uses_codex_settings_from_config() -> None:
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {
                "command": "custom-codex app-server",
                "approval_policy": "never",
                "turn_timeout_ms": 42,
            },
        }
    )
    backend = create_default_registry(config).get("codex")

    assert isinstance(backend, CodexBackend)
    assert backend.command == "custom-codex app-server"
    assert backend.approval_policy == "never"
    assert backend.turn_timeout_ms == 42


def test_turn_result_tracks_events() -> None:
    event = AgentEvent(
        provider="codex",
        session_id="codex:thread-1",
        kind="turn.completed",
        occurred_at=AgentTurnResult.now(),
    )

    result = AgentTurnResult(session_id="codex:thread-1", events=(event,))

    assert result.events == (event,)
