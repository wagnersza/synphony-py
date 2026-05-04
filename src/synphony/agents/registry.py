"""Agent backend registry keyed by workflow provider id."""

from __future__ import annotations

from collections.abc import Callable

from synphony.agents.base import AgentBackend
from synphony.errors import AgentNotFoundError

BackendFactory = Callable[[], AgentBackend]


class AgentBackendRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, BackendFactory] = {}

    def register(self, provider: str, factory: BackendFactory) -> None:
        self._factories[provider] = factory

    def create(self, provider: str) -> AgentBackend:
        try:
            return self._factories[provider]()
        except KeyError as exc:
            raise AgentNotFoundError(f"unsupported agent provider: {provider}") from exc
