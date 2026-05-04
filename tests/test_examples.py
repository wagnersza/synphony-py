from pathlib import Path

from synphony.config import SynphonyConfig
from synphony.workflow import load_workflow


def test_example_workflows_parse_and_validate() -> None:
    example_paths = sorted(Path("docs/examples").glob("WORKFLOW.*.md"))

    assert {path.name for path in example_paths} == {
        "WORKFLOW.claude.md",
        "WORKFLOW.codex.md",
    }
    for path in example_paths:
        workflow = load_workflow(path)
        config = SynphonyConfig.from_mapping(workflow.config)

        assert config.tracker_kind == "jira"
        assert config.agent_provider in {"claude", "codex"}
        assert config.provider_command
        assert "{{ issue.identifier }}" in workflow.prompt_template
