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


def test_minimal_no_front_matter_workflow_parses_as_prompt(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text("Work on {{ issue.identifier }}.", encoding="utf-8")

    workflow = load_workflow(workflow_path)

    assert workflow.config == {}
    assert workflow.prompt_template == "Work on {{ issue.identifier }}."
