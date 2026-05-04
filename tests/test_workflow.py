from pathlib import Path

import pytest

from synphony.errors import TemplateRenderError, WorkflowNotFoundError, WorkflowParseError
from synphony.models import Issue, RunAttempt
from synphony.prompt import render_prompt
from synphony.workflow import load_workflow


def test_load_workflow_parses_front_matter_and_prompt(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        """---
tracker:
  kind: jira
  jql: project = DEMO
agent:
  provider: codex
codex:
  command: codex app-server
---
Work on {{ issue.identifier }} attempt {{ attempt.number }}.
""",
        encoding="utf-8",
    )

    workflow = load_workflow(workflow_path)

    assert workflow.path == str(workflow_path)
    assert workflow.config["tracker"]["kind"] == "jira"
    assert workflow.prompt_template.strip() == (
        "Work on {{ issue.identifier }} attempt {{ attempt.number }}."
    )


def test_load_workflow_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(WorkflowNotFoundError):
        load_workflow(tmp_path / "missing.md")


def test_load_workflow_accepts_missing_front_matter_as_prompt(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text("\n\nNo front matter\n", encoding="utf-8")

    workflow = load_workflow(workflow_path)

    assert workflow.config == {}
    assert workflow.prompt_template == "No front matter"


def test_load_workflow_trims_front_matter_prompt_body(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        """---
tracker:
  kind: jira
agent:
  provider: claude
claude:
  command: claude
---

Prompt body

""",
        encoding="utf-8",
    )

    workflow = load_workflow(workflow_path)

    assert workflow.prompt_template == "Prompt body"


def test_load_workflow_rejects_non_mapping_front_matter(tmp_path: Path) -> None:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        """---
- not
- a
- map
---
Prompt
""",
        encoding="utf-8",
    )

    with pytest.raises(WorkflowParseError, match="YAML mapping"):
        load_workflow(workflow_path)


def test_render_prompt_replaces_known_variables(make_issue: Issue) -> None:
    attempt = RunAttempt(issue_id=make_issue.id, issue_identifier=make_issue.identifier, attempt=2)

    rendered = render_prompt(
        "Fix {{ issue.identifier }}: {{ issue.title }} on attempt {{ attempt.number }}.",
        issue=make_issue,
        attempt=attempt,
    )

    assert rendered == "Fix DEMO-1: Add tests on attempt 2."


def test_render_prompt_rejects_unknown_variables(make_issue: Issue) -> None:
    attempt = RunAttempt(issue_id=make_issue.id, issue_identifier=make_issue.identifier, attempt=1)

    with pytest.raises(TemplateRenderError, match="unknown variable"):
        render_prompt("{{ issue.unknown }}", issue=make_issue, attempt=attempt)
