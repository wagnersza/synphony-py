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
    def workspace_root(self) -> str:
        value = self._optional_str(("workspace", "root")) or ".synphony/workspaces"
        return str(Path(self._resolve_env(value)).expanduser())

    @property
    def polling_interval_ms(self) -> int:
        return self._optional_int(("polling", "interval_ms"), default=5000)

    @property
    def active_states(self) -> list[str]:
        return self._optional_str_list(("workflow", "active_states"), default=["Ready"])

    @property
    def terminal_states(self) -> list[str]:
        return self._optional_str_list(("workflow", "terminal_states"), default=["Done"])

    @property
    def agent_max_turns(self) -> int:
        return self._optional_int(("agent", "max_turns"), default=1)

    @property
    def agent_max_concurrent_agents(self) -> int:
        return self._optional_int(("agent", "max_concurrent_agents"), default=1)

    @property
    def agent_max_concurrent_agents_by_state(self) -> dict[str, int]:
        return self._optional_int_mapping(("agent", "max_concurrent_agents_by_state"))

    @property
    def agent_initial_retry_backoff_ms(self) -> int:
        return self._optional_int(("agent", "initial_retry_backoff_ms"), default=1000)

    @property
    def agent_max_retry_backoff_ms(self) -> int:
        return self._optional_int(("agent", "max_retry_backoff_ms"), default=60000)

    @property
    def agent_stall_timeout_ms(self) -> int:
        return self._optional_int(("agent", "stall_timeout_ms"), default=60000)

    @property
    def workspace_hooks(self) -> dict[str, str]:
        value = self._lookup(("workspace", "hooks"), required=False)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ConfigValidationError("workspace.hooks must be a mapping")
        hooks: dict[str, str] = {}
        for key, command in value.items():
            if not isinstance(key, str) or not isinstance(command, str):
                raise ConfigValidationError("workspace.hooks must map strings to strings")
            hooks[key] = self._resolve_env(command)
        return hooks

    @property
    def workspace_hook_timeout_ms(self) -> int:
        return self._optional_int(("workspace", "hook_timeout_ms"), default=30000)

    def _validate(self) -> None:
        if self.tracker_kind != "jira":
            raise ConfigValidationError("tracker.kind must be 'jira'")
        if self.agent_provider not in {"codex", "claude"}:
            raise ConfigValidationError("agent.provider must be 'codex' or 'claude'")
        if not self.provider_command.strip():
            raise ConfigValidationError(f"{self.agent_provider}.command must not be empty")
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

    def _optional_str_list(self, path: tuple[str, ...], *, default: list[str]) -> list[str]:
        value = self._lookup(path, required=False)
        if value is None:
            return list(default)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ConfigValidationError(f"{'.'.join(path)} must be a list of strings")
        return [self._resolve_env(item) for item in value]

    def _optional_int_mapping(self, path: tuple[str, ...]) -> dict[str, int]:
        value = self._lookup(path, required=False)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ConfigValidationError(f"{'.'.join(path)} must be a mapping")
        output: dict[str, int] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not isinstance(item, int):
                raise ConfigValidationError(f"{'.'.join(path)} must map strings to integers")
            output[key] = item
        return output

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
