"""Agent backend registry construction."""

from __future__ import annotations

from synphony.agents.base import AgentBackendRegistry
from synphony.agents.claude import ClaudeBackend, ClaudeBackendConfig


def build_agent_backend_registry(
    *,
    claude: ClaudeBackendConfig | None = None,
) -> AgentBackendRegistry:
    registry = AgentBackendRegistry()
    registry.register("claude", lambda: ClaudeBackend(claude or ClaudeBackendConfig()))
    return registry
