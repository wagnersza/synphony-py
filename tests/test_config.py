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


_BASE_CONFIG: dict[str, object] = {
    "tracker": {"kind": "jira", "jql": "project = DEMO"},
    "agent": {"provider": "codex"},
    "codex": {"command": "codex app-server"},
}


def test_workspace_root_resolves_relative_to_workflow_dir(tmp_path: Path) -> None:
    config = SynphonyConfig.from_mapping(
        {**_BASE_CONFIG, "workspace": {"root": ".synphony/workspaces"}},
        workflow_dir=tmp_path,
    )

    assert config.workspace_root == str(tmp_path / ".synphony/workspaces")


def test_workspace_root_default_resolves_relative_to_workflow_dir(tmp_path: Path) -> None:
    config = SynphonyConfig.from_mapping(_BASE_CONFIG, workflow_dir=tmp_path)

    assert config.workspace_root == str(tmp_path / ".synphony/workspaces")


def test_workspace_root_absolute_path_ignores_workflow_dir(tmp_path: Path) -> None:
    config = SynphonyConfig.from_mapping(
        {**_BASE_CONFIG, "workspace": {"root": "/absolute/path"}},
        workflow_dir=tmp_path,
    )

    assert config.workspace_root == "/absolute/path"


def test_workspace_root_tilde_ignores_workflow_dir(tmp_path: Path) -> None:
    config = SynphonyConfig.from_mapping(
        {**_BASE_CONFIG, "workspace": {"root": "~/synphony-work"}},
        workflow_dir=tmp_path,
    )

    assert config.workspace_root == str(Path("~/synphony-work").expanduser())


def test_workspace_root_env_var_ignores_workflow_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SYNPHONY_ROOT", "/env/path")

    config = SynphonyConfig.from_mapping(
        {**_BASE_CONFIG, "workspace": {"root": "$SYNPHONY_ROOT"}},
        workflow_dir=tmp_path,
    )

    assert config.workspace_root == "/env/path"


def test_workspace_root_relative_without_workflow_dir_stays_relative() -> None:
    config = SynphonyConfig.from_mapping(
        {**_BASE_CONFIG, "workspace": {"root": ".synphony/workspaces"}},
    )

    assert config.workspace_root == ".synphony/workspaces"


def test_provider_command_is_not_env_expanded() -> None:
    # Non-path command strings with $ should not be env-expanded accidentally.
    # The current policy only expands bare "$VAR" (entire string is the ref).
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira"},
            "agent": {"provider": "codex"},
            "codex": {"command": "codex --arg $SOME_VAR"},
        }
    )

    assert config.provider_command == "codex --arg $SOME_VAR"
