"""Registry for agent backend implementations."""

from __future__ import annotations

from synphony.agents.base import AgentBackend
from synphony.agents.claude import ClaudeBackend, ClaudeBackendConfig
from synphony.agents.codex import CodexBackend
from synphony.config import SynphonyConfig
from synphony.errors import AgentNotFoundError


class AgentRegistry:
    """Small provider-id registry used by config and the runner."""

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


def create_default_registry(config: SynphonyConfig | None = None) -> AgentRegistry:
    registry = AgentRegistry()
    registry.register(_build_codex_backend(config))
    registry.register(_build_claude_backend(config))
    return registry


def _build_codex_backend(config: SynphonyConfig | None) -> CodexBackend:
    if config is None or "codex" not in config.raw:
        return CodexBackend()
    return CodexBackend(
        command=config.codex_command,
        approval_policy=config.codex_approval_policy,
        thread_sandbox=config.codex_thread_sandbox,
        turn_sandbox_policy=config.codex_turn_sandbox_policy,
        read_timeout_ms=config.codex_read_timeout_ms,
        turn_timeout_ms=config.codex_turn_timeout_ms,
    )


def _build_claude_backend(config: SynphonyConfig | None) -> ClaudeBackend:
    if config is None or "claude" not in config.raw:
        return ClaudeBackend(ClaudeBackendConfig())
    return ClaudeBackend(
        ClaudeBackendConfig(
            command=config.claude_command,
            turn_timeout_ms=config.claude_turn_timeout_ms,
            stall_timeout_ms=config.claude_stall_timeout_ms,
            bare=config.claude_bare,
            verbose=config.claude_verbose,
            include_partial_messages=config.claude_include_partial_messages,
            permission_mode=config.claude_permission_mode,
            allowed_tools=tuple(config.claude_allowed_tools),
            max_turns=config.claude_max_turns,
            extra_args=tuple(config.claude_extra_args),
        )
    )
