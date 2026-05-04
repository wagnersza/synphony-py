"""Registry for agent backend implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from synphony.agents.base import AgentBackend, AgentTurnInput, AgentTurnResult
from synphony.errors import AgentNotFoundError, AgentProtocolError


class AgentRegistry:
    """Small provider-id registry used by config and the future runner."""

    def __init__(self) -> None:
        self._backends: dict[str, AgentBackend] = {}

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(self._backends)

    def register(self, backend: AgentBackend) -> None:
        if backend.provider in self._backends:
            raise ValueError(f"agent provider is already registered: {backend.provider}")
        self._backends[backend.provider] = backend

    def get(self, provider: str) -> AgentBackend:
        try:
            return self._backends[provider]
        except KeyError as exc:
            raise AgentNotFoundError(
                f"unsupported agent provider: {provider}",
                details={"provider": provider},
            ) from exc


@dataclass(frozen=True, slots=True)
class _ReservedProviderBackend:
    """Registry placeholder until real provider adapters land in Phase 5."""

    provider: str

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        raise AgentProtocolError(
            f"{self.provider} backend is not implemented yet",
            details={"provider": self.provider},
        )

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        raise AgentProtocolError(
            f"{self.provider} backend is not implemented yet",
            details={"provider": self.provider},
        )

    def stop_session(self, session_id: str, *, timeout: timedelta | None = None) -> None:
        return None


def create_default_registry() -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(_ReservedProviderBackend(provider="codex"))
    registry.register(_ReservedProviderBackend(provider="claude"))
    return registry
