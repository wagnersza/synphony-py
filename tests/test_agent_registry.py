from synphony.agents.base import AgentBackendRegistry
from synphony.agents.claude import ClaudeBackend, ClaudeBackendConfig
from synphony.agents.registry import build_agent_backend_registry
from synphony.errors import AgentNotFoundError


def test_agent_backend_registry_dispatches_registered_backend() -> None:
    backend = object()
    registry = AgentBackendRegistry()
    registry.register("claude", lambda: backend)

    assert registry.create("claude") is backend


def test_agent_backend_registry_rejects_unknown_provider() -> None:
    registry = AgentBackendRegistry()

    try:
        registry.create("opencode")
    except AgentNotFoundError as exc:
        assert exc.details == {"provider": "opencode"}
    else:
        raise AssertionError("expected AgentNotFoundError")


def test_default_agent_backend_registry_includes_claude_backend() -> None:
    registry = build_agent_backend_registry(claude=ClaudeBackendConfig(command="claude"))

    assert isinstance(registry.create("claude"), ClaudeBackend)
