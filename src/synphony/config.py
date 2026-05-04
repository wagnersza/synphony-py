"""Typed access to workflow configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeGuard, cast

from synphony.errors import ConfigValidationError

AgentProvider = Literal["codex", "claude"]


@dataclass(frozen=True, slots=True)
class SynphonyConfig:
    raw: dict[str, Any]
    workflow_path: Path | None = None

    @classmethod
    def from_mapping(
        cls,
        mapping: dict[str, Any],
        *,
        workflow_path: str | Path | None = None,
    ) -> SynphonyConfig:
        config = cls(raw=mapping, workflow_path=Path(workflow_path) if workflow_path else None)
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
    def provider_timeout_ms(self) -> int | None:
        return self._optional_positive_int_or_none((self.agent_provider, "timeout_ms"))

    @property
    def workspace_root(self) -> str:
        value = self._optional_str(("workspace", "root")) or ".synphony/workspaces"
        path = Path(self._resolve_path_vars(value, field_path="workspace.root")).expanduser()
        if path.is_absolute() or self.workflow_path is None:
            return str(path)
        return str(self.workflow_path.expanduser().resolve().parent / path)

    @property
    def polling_interval_ms(self) -> int:
        return self._optional_positive_int(("polling", "interval_ms"), default=5000)

    @property
    def active_state_names(self) -> tuple[str, ...]:
        return self._optional_str_tuple(("tracker", "active_states"), default=("Ready",))

    @property
    def terminal_state_names(self) -> tuple[str, ...]:
        return self._optional_str_tuple(
            ("tracker", "terminal_states"),
            default=("Done", "Canceled"),
        )

    @property
    def max_concurrent_agents(self) -> int:
        return self._optional_positive_int(("agent", "max_concurrent_agents"), default=1)

    @property
    def max_concurrent_agents_by_state(self) -> dict[str, int]:
        return self._optional_str_int_map(("agent", "max_concurrent_agents_by_state"))

    @property
    def agent_max_turns(self) -> int:
        return self._optional_positive_int(("agent", "max_turns"), default=20)

    @property
    def agent_max_retry_backoff_ms(self) -> int:
        return self._optional_positive_int(("agent", "max_retry_backoff_ms"), default=60_000)

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
        return self._optional_positive_int(("hooks", "timeout_ms"), default=60_000)

    def _validate(self) -> None:
        if self.tracker_kind != "jira":
            raise ConfigValidationError("tracker.kind must be 'jira'")
        if self.agent_provider not in {"codex", "claude"}:
            raise ConfigValidationError("agent.provider must be 'codex' or 'claude'")
        if not self.provider_command.strip():
            raise ConfigValidationError(f"{self.agent_provider}.command must not be empty")
        if self._lookup(("workspace", "hooks"), required=False) is not None:
            raise ConfigValidationError("workspace.hooks is unsupported; use top-level hooks")
        _ = self.workspace_root
        _ = self.polling_interval_ms
        _ = self.active_state_names
        _ = self.terminal_state_names
        _ = self.max_concurrent_agents
        _ = self.max_concurrent_agents_by_state
        _ = self.agent_max_turns
        _ = self.agent_max_retry_backoff_ms
        _ = self.hook_after_create
        _ = self.hook_before_run
        _ = self.hook_after_run
        _ = self.hook_before_remove
        _ = self.hook_timeout_ms
        _ = self.provider_timeout_ms

    def _required_str(self, path: tuple[str, ...]) -> str:
        value = self._lookup(path)
        if not isinstance(value, str):
            raise ConfigValidationError(f"{'.'.join(path)} must be a string")
        return value

    def _optional_str(self, path: tuple[str, ...]) -> str | None:
        value = self._lookup(path, required=False)
        if value is None:
            return None
        if not isinstance(value, str):
            raise ConfigValidationError(f"{'.'.join(path)} must be a string")
        return value

    def _optional_positive_int(
        self,
        path: tuple[str, ...],
        *,
        default: int,
    ) -> int:
        value = self._lookup(path, required=False)
        if value is None:
            return default
        return self._validate_positive_int(path, value)

    def _optional_positive_int_or_none(self, path: tuple[str, ...]) -> int | None:
        value = self._lookup(path, required=False)
        if value is None:
            return None
        return self._validate_positive_int(path, value)

    def _validate_positive_int(self, path: tuple[str, ...], value: Any) -> int:
        if not _is_plain_int(value):
            raise ConfigValidationError(f"{'.'.join(path)} must be an integer")
        if value < 1:
            raise ConfigValidationError(f"{'.'.join(path)} must be at least 1")
        return value

    def _optional_str_tuple(
        self,
        path: tuple[str, ...],
        *,
        default: tuple[str, ...],
    ) -> tuple[str, ...]:
        value = self._lookup(path, required=False)
        if value is None:
            return default
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ConfigValidationError(f"{'.'.join(path)} must be a list of strings")
        return tuple(value)

    def _optional_str_int_map(self, path: tuple[str, ...]) -> dict[str, int]:
        value = self._lookup(path, required=False)
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ConfigValidationError(f"{'.'.join(path)} must be a mapping")

        result: dict[str, int] = {}
        for key, cap in value.items():
            if not isinstance(key, str):
                raise ConfigValidationError(f"{'.'.join(path)} keys must be strings")
            if not _is_plain_int(cap):
                raise ConfigValidationError(f"{'.'.join(path)}.{key} must be an integer")
            if cap < 1:
                raise ConfigValidationError(f"{'.'.join(path)}.{key} must be at least 1")
            result[key] = cap
        return result

    def _lookup(self, path: tuple[str, ...], *, required: bool = True) -> Any:
        current: Any = self.raw
        for key in path:
            if not isinstance(current, dict) or key not in current:
                if required:
                    raise ConfigValidationError(f"{'.'.join(path)} is required")
                return None
            current = current[key]
        return current

    def _resolve_path_vars(self, value: str, *, field_path: str) -> str:
        for match in re.finditer(r"\$(\w+)|\$\{([^}]+)\}", value):
            env_name = match.group(1) or match.group(2)
            if not env_name:
                raise ConfigValidationError(
                    f"{field_path} environment reference must include a name"
                )
            if env_name not in os.environ:
                raise ConfigValidationError(f"environment variable {env_name} is not set")
        return os.path.expandvars(value)


def _is_plain_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)
