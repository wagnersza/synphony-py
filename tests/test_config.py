from pathlib import Path
from typing import Any

import pytest

from synphony.config import SynphonyConfig
from synphony.errors import ConfigValidationError


def test_config_validates_jira_and_selected_codex_provider() -> None:
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {"command": "codex app-server"},
        }
    )

    assert config.tracker_kind == "jira"
    assert config.agent_provider == "codex"
    assert config.provider_command == "codex app-server"
    assert config.polling_interval_ms == 5000
    assert config.active_state_names == ("Ready",)
    assert config.terminal_state_names == ("Done", "Canceled")
    assert config.max_concurrent_agents == 1
    assert config.max_concurrent_agents_by_state == {}
    assert config.agent_max_turns == 20
    assert config.agent_max_retry_backoff_ms == 60_000
    assert config.hook_timeout_ms == 60_000
    assert config.provider_timeout_ms is None


def test_config_validates_selected_claude_provider() -> None:
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "claude"},
            "claude": {"command": "claude --print"},
        }
    )

    assert config.agent_provider == "claude"
    assert config.provider_command == "claude --print"


def test_config_rejects_unsupported_tracker() -> None:
    with pytest.raises(ConfigValidationError, match="tracker.kind"):
        SynphonyConfig.from_mapping(
            {
                "tracker": {"kind": "linear"},
                "agent": {"provider": "codex"},
                "codex": {"command": "codex app-server"},
            }
        )


def test_config_rejects_unsupported_provider() -> None:
    with pytest.raises(ConfigValidationError, match="agent.provider"):
        SynphonyConfig.from_mapping(
            {
                "tracker": {"kind": "jira", "jql": "project = DEMO"},
                "agent": {"provider": "opencode"},
            }
        )


def test_config_resolves_allowed_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNPHONY_WORKSPACE_ROOT", "~/synphony-work")

    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {"command": "codex app-server"},
            "workspace": {"root": "$SYNPHONY_WORKSPACE_ROOT"},
        }
    )

    assert config.workspace_root == str(Path("~/synphony-work").expanduser())


def test_config_resolves_workspace_root_relative_to_workflow_file(tmp_path: Path) -> None:
    workflow_dir = tmp_path / "workflows"
    workflow_dir.mkdir()
    workflow_path = workflow_dir / "WORKFLOW.md"

    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {"command": "codex app-server"},
            "workspace": {"root": ".synphony/workspaces"},
        },
        workflow_path=workflow_path,
    )

    assert Path(config.workspace_root) == workflow_dir / ".synphony" / "workspaces"


def test_config_does_not_expand_env_vars_in_command_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SYNPHONY_CODEX_COMMAND", "unexpected")

    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {"command": "$SYNPHONY_CODEX_COMMAND"},
        }
    )

    assert config.provider_command == "$SYNPHONY_CODEX_COMMAND"


def test_config_rejects_unset_env_vars() -> None:
    with pytest.raises(ConfigValidationError, match="UNSET_ROOT"):
        SynphonyConfig.from_mapping(
            {
                "tracker": {"kind": "jira", "jql": "project = DEMO"},
                "agent": {"provider": "codex"},
                "codex": {"command": "codex app-server"},
                "workspace": {"root": "$UNSET_ROOT"},
            }
        )


def test_config_reads_runtime_fields_and_top_level_hooks() -> None:
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {
                "kind": "jira",
                "jql": "project = DEMO",
                "active_states": ["Ready", "In Progress"],
                "terminal_states": ["Done"],
            },
            "polling": {"interval_ms": 10_000},
            "agent": {
                "provider": "claude",
                "max_turns": 8,
                "max_concurrent_agents": 3,
                "max_concurrent_agents_by_state": {"Ready": 2, "In Progress": 1},
                "max_retry_backoff_ms": 120_000,
            },
            "hooks": {
                "after_create": "uv sync",
                "before_run": "pytest",
                "after_run": "git status --short",
                "before_remove": "echo removing",
                "timeout_ms": 45_000,
            },
            "claude": {"command": "claude", "timeout_ms": 300_000},
        }
    )

    assert config.active_state_names == ("Ready", "In Progress")
    assert config.terminal_state_names == ("Done",)
    assert config.polling_interval_ms == 10_000
    assert config.max_concurrent_agents == 3
    assert config.max_concurrent_agents_by_state == {"Ready": 2, "In Progress": 1}
    assert config.agent_max_turns == 8
    assert config.agent_max_retry_backoff_ms == 120_000
    assert config.hook_after_create == "uv sync"
    assert config.hook_before_run == "pytest"
    assert config.hook_after_run == "git status --short"
    assert config.hook_before_remove == "echo removing"
    assert config.hook_timeout_ms == 45_000
    assert config.provider_timeout_ms == 300_000


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"polling": {"interval_ms": 0}}, "polling.interval_ms"),
        ({"agent": {"max_turns": 0}}, "agent.max_turns"),
        ({"agent": {"max_concurrent_agents": 0}}, "agent.max_concurrent_agents"),
        (
            {"agent": {"max_concurrent_agents_by_state": {"Ready": 0}}},
            "agent.max_concurrent_agents_by_state.Ready",
        ),
        ({"agent": {"max_retry_backoff_ms": 0}}, "agent.max_retry_backoff_ms"),
        ({"hooks": {"timeout_ms": 0}}, "hooks.timeout_ms"),
        ({"codex": {"timeout_ms": 0}}, "codex.timeout_ms"),
    ],
)
def test_config_rejects_invalid_numeric_ranges(
    override: dict[str, Any],
    message: str,
) -> None:
    mapping: dict[str, Any] = {
        "tracker": {"kind": "jira", "jql": "project = DEMO"},
        "agent": {"provider": "codex"},
        "codex": {"command": "codex app-server"},
    }
    _deep_update(mapping, override)

    with pytest.raises(ConfigValidationError, match=message):
        SynphonyConfig.from_mapping(mapping)


def test_config_rejects_workspace_hooks_block() -> None:
    with pytest.raises(ConfigValidationError, match="workspace.hooks"):
        SynphonyConfig.from_mapping(
            {
                "tracker": {"kind": "jira", "jql": "project = DEMO"},
                "agent": {"provider": "codex"},
                "codex": {"command": "codex app-server"},
                "workspace": {"hooks": {"before_run": "uv sync"}},
            }
        )


def _deep_update(target: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        existing = target.get(key)
        if isinstance(value, dict) and isinstance(existing, dict):
            _deep_update(existing, value)
        else:
            target[key] = value
