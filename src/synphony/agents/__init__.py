"""Agent backend boundary and provider registry."""

from synphony.agents.base import AgentBackend, AgentTurnInput, AgentTurnRequest, AgentTurnResult
from synphony.agents.claude import ClaudeBackend, ClaudeBackendConfig
from synphony.agents.codex import CodexBackend
from synphony.agents.registry import AgentRegistry, create_default_registry

__all__ = [
    "AgentBackend",
    "AgentRegistry",
    "AgentTurnInput",
    "AgentTurnRequest",
    "AgentTurnResult",
    "ClaudeBackend",
    "ClaudeBackendConfig",
    "CodexBackend",
    "create_default_registry",
]
