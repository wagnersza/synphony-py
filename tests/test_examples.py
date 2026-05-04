from pathlib import Path

import pytest

from synphony.config import SynphonyConfig
from synphony.workflow import load_workflow


@pytest.mark.parametrize(
    ("path", "provider", "command"),
    [
        ("docs/examples/WORKFLOW.codex.md", "codex", "codex app-server"),
        ("docs/examples/WORKFLOW.claude.md", "claude", "claude --print"),
    ],
)
def test_example_workflows_parse_and_validate(path: str, provider: str, command: str) -> None:
    workflow = load_workflow(Path(path))
    config = SynphonyConfig.from_mapping(workflow.config)

    assert config.tracker_kind == "jira"
    assert config.agent_provider == provider
    assert config.provider_command == command
    assert workflow.prompt_template.strip()
