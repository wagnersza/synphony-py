from pathlib import Path

from synphony.workflow_store import WorkflowStore


def test_workflow_store_loads_initial_workflow(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path, "project = DEMO")

    store = WorkflowStore(workflow_path)
    result = store.load()

    assert result.changed is True
    assert result.workflow is not None
    assert result.workflow.config["tracker"]["jql"] == "project = DEMO"
    assert result.error is None


def test_workflow_store_returns_unchanged_when_file_did_not_change(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path, "project = DEMO")
    store = WorkflowStore(workflow_path)

    store.load()
    result = store.reload_if_changed()

    assert result.changed is False
    assert result.workflow is not None
    assert result.error is None


def test_workflow_store_reloads_changed_workflow(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path, "project = DEMO")
    store = WorkflowStore(workflow_path)
    store.load()

    _write_workflow(tmp_path, "project = OTHER")
    result = store.reload_if_changed()

    assert result.changed is True
    assert result.workflow is not None
    assert result.workflow.config["tracker"]["jql"] == "project = OTHER"
    assert result.error is None


def test_workflow_store_keeps_last_good_workflow_on_invalid_reload(tmp_path: Path) -> None:
    workflow_path = _write_workflow(tmp_path, "project = DEMO")
    store = WorkflowStore(workflow_path)
    initial = store.load().workflow

    workflow_path.write_text(
        """---
- invalid
---
Prompt
""",
        encoding="utf-8",
    )
    result = store.reload_if_changed()

    assert result.changed is False
    assert result.workflow == initial
    assert result.error is not None


def _write_workflow(tmp_path: Path, jql: str) -> Path:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        f"""---
tracker:
  kind: jira
  jql: {jql}
agent:
  provider: codex
codex:
  command: codex app-server
---
Prompt
""",
        encoding="utf-8",
    )
    return workflow_path
