"""Registry for agent backend implementations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from synphony.agents.base import AgentBackend, AgentTurnInput, AgentTurnResult
from synphony.agents.codex import CodexBackend
from synphony.config import SynphonyConfig
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


def create_default_registry(config: SynphonyConfig | None = None) -> AgentRegistry:
    registry = AgentRegistry()
    if config is None:
        registry.register(CodexBackend())
    else:
        registry.register(
            CodexBackend(
                command=config.codex_command,
                approval_policy=config.codex_approval_policy,
                thread_sandbox=config.codex_thread_sandbox,
                turn_sandbox_policy=config.codex_turn_sandbox_policy,
                read_timeout_ms=config.codex_read_timeout_ms,
                turn_timeout_ms=config.codex_turn_timeout_ms,
            )
        )
    registry.register(_ReservedProviderBackend(provider="claude"))
    return registry
