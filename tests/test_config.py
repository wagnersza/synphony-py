from pathlib import Path

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


def test_config_reads_top_level_hook_commands_and_timeout() -> None:
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {"command": "codex app-server"},
            "hooks": {
                "after_create": "echo created",
                "before_run": "uv sync",
                "after_run": "echo done",
                "before_remove": "echo remove",
                "timeout_ms": 2500,
            },
        }
    )

    assert config.hook_after_create == "echo created"
    assert config.hook_before_run == "uv sync"
    assert config.hook_after_run == "echo done"
    assert config.hook_before_remove == "echo remove"
    assert config.hook_timeout_ms == 2500
    assert config.hook_timeout_s == 2.5


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
