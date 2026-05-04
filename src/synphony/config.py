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
    def hook_after_create(self) -> str | None:
        return self._optional_str(("hooks", "after_create"))

    @property
    def hook_before_run(self) -> str | None:
        return self._optional_str(("hooks", "before_run"))

    @property
    def hook_after_run(self) -> str | None:
        return self._optional_str(("hooks", "after_run"))

    @property
    def hook_before_remove(self) -> str | None:
        return self._optional_str(("hooks", "before_remove"))

    @property
    def hook_timeout_ms(self) -> int:
        return self._optional_positive_int(("hooks", "timeout_ms"), default=60000)

    @property
    def hook_timeout_s(self) -> float:
        return self.hook_timeout_ms / 1000

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
        _ = self.workspace_root
        self._validate_hooks()
        _ = self.hook_timeout_ms

    def _validate_hooks(self) -> None:
        hooks = self._lookup(("hooks",), required=False)
        if hooks is not None and not isinstance(hooks, dict):
            raise ConfigValidationError("hooks must be a mapping")
        workspace_hooks = self._lookup(("workspace", "hooks"), required=False)
        if workspace_hooks is not None:
            raise ConfigValidationError("workspace.hooks is unsupported; use top-level hooks")

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

    def _optional_positive_int(self, path: tuple[str, ...], *, default: int) -> int:
        value = self._optional_int(path, default=default)
        if value < 1:
            raise ConfigValidationError(f"{'.'.join(path)} must be at least 1")
        return value

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
