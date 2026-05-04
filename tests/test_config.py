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


def test_config_exposes_codex_runtime_settings() -> None:
    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {
                "command": "codex --config model=gpt-5.5 app-server",
                "approval_policy": "never",
                "thread_sandbox": "read-only",
                "turn_sandbox_policy": {"type": "workspaceWrite", "networkAccess": False},
                "read_timeout_ms": 1234,
                "turn_timeout_ms": 5678,
            },
        }
    )

    assert config.codex_command == "codex --config model=gpt-5.5 app-server"
    assert config.codex_approval_policy == "never"
    assert config.codex_thread_sandbox == "read-only"
    assert config.codex_turn_sandbox_policy == {"type": "workspaceWrite", "networkAccess": False}
    assert config.codex_read_timeout_ms == 1234
    assert config.codex_turn_timeout_ms == 5678


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
