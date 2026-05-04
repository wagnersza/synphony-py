"""Agent backend boundary and provider registry."""

from synphony.agents.base import AgentBackend, AgentTurnInput, AgentTurnResult
from synphony.agents.registry import AgentRegistry, create_default_registry

__all__ = [
    "AgentBackend",
    "AgentRegistry",
    "AgentTurnInput",
    "AgentTurnResult",
    "create_default_registry",
]
