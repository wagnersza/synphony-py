"""Typed access to workflow configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from synphony.errors import ConfigValidationError

AgentProvider = Literal["codex", "claude"]


@dataclass(frozen=True, slots=True)
class SynphonyConfig:
    raw: dict[str, Any]

    @classmethod
    def from_mapping(cls, mapping: dict[str, Any]) -> SynphonyConfig:
        config = cls(raw=mapping)
        config._validate()
        return config

    @property
    def tracker_kind(self) -> str:
        return self._required_str(("tracker", "kind"))

    @property
    def tracker_jql(self) -> str | None:
        return self._optional_str(("tracker", "jql"))

    @property
    def agent_provider(self) -> AgentProvider:
        return cast(AgentProvider, self._required_str(("agent", "provider")))

    @property
    def provider_command(self) -> str:
        return self._required_str((self.agent_provider, "command"))

    @property
    def codex_command(self) -> str:
        return self._required_str(("codex", "command"))

    @property
    def codex_approval_policy(self) -> str | dict[str, Any] | None:
        return self._optional_str_or_mapping(("codex", "approval_policy"))

    @property
    def codex_thread_sandbox(self) -> str | dict[str, Any] | None:
        return self._optional_str_or_mapping(("codex", "thread_sandbox"))

    @property
    def codex_turn_sandbox_policy(self) -> str | dict[str, Any] | None:
        return self._optional_str_or_mapping(("codex", "turn_sandbox_policy"))

    @property
    def codex_read_timeout_ms(self) -> int:
        return self._optional_int(("codex", "read_timeout_ms"), default=30000)

    @property
    def codex_turn_timeout_ms(self) -> int:
        return self._optional_int(("codex", "turn_timeout_ms"), default=3600000)

    @property
    def workspace_root(self) -> str:
        value = self._optional_str(("workspace", "root")) or ".synphony/workspaces"
        return str(Path(self._resolve_env(value)).expanduser())

    @property
    def polling_interval_ms(self) -> int:
        return self._optional_int(("polling", "interval_ms"), default=5000)

    def _validate(self) -> None:
        if self.tracker_kind != "jira":
            raise ConfigValidationError("tracker.kind must be 'jira'")
        if self.agent_provider not in {"codex", "claude"}:
            raise ConfigValidationError("agent.provider must be 'codex' or 'claude'")
        if not self.provider_command.strip():
            raise ConfigValidationError(f"{self.agent_provider}.command must not be empty")
        if self.agent_provider == "codex":
            _ = self.codex_approval_policy
            _ = self.codex_thread_sandbox
            _ = self.codex_turn_sandbox_policy
            _ = self.codex_read_timeout_ms
            _ = self.codex_turn_timeout_ms
        _ = self.workspace_root

    def _required_str(self, path: tuple[str, ...]) -> str:
        value = self._lookup(path)
        if not isinstance(value, str):
            raise ConfigValidationError(f"{'.'.join(path)} must be a string")
        return self._resolve_env(value)

    def _optional_str(self, path: tuple[str, ...]) -> str | None:
        value = self._lookup(path, required=False)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigValidationError(f"{'.'.join(path)} must be a string")
        return self._resolve_env(value)

    def _optional_int(self, path: tuple[str, ...], *, default: int) -> int:
        value = self._lookup(path, required=False)
        if value is None:
            return default
        if not isinstance(value, int):
            raise ConfigValidationError(f"{'.'.join(path)} must be an integer")
        return value

    def _optional_str_or_mapping(self, path: tuple[str, ...]) -> str | dict[str, Any] | None:
        value = self._lookup(path, required=False)
        if value is None:
            return None
        if isinstance(value, str):
            return self._resolve_env(value)
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
        raise ConfigValidationError(f"{'.'.join(path)} must be a string or mapping")

    def _lookup(self, path: tuple[str, ...], *, required: bool = True) -> Any:
        current: Any = self.raw
        for key in path:
            if not isinstance(current, dict) or key not in current:
                if required:
                    raise ConfigValidationError(f"{'.'.join(path)} is required")
                return None
            current = current[key]
        return current

    def _resolve_env(self, value: str) -> str:
        if not value.startswith("$"):
            return value

        env_name = value[1:]
        if not env_name:
            raise ConfigValidationError("environment variable reference must include a name")
        resolved = os.environ.get(env_name)
        if resolved is None:
            raise ConfigValidationError(f"environment variable {env_name} is not set")
        return resolved
