from __future__ import annotations

from pathlib import Path

import pytest

from synphony.cli import main


def test_cli_check_validates_workflow_config(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_path = _write_workflow(tmp_path, provider="codex", command="codex app-server")

    exit_code = main(["--check", str(workflow_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "workflow ok" in captured.out
    assert str(workflow_path) in captured.out


def test_cli_reports_validation_errors_with_nonzero_exit(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_path = _write_workflow(tmp_path, provider="opencode", command="opencode")

    exit_code = main(["--check", str(workflow_path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "config_validation_error" in captured.err
    assert "agent.provider" in captured.err


def test_cli_run_mode_fails_clearly_until_real_backends_exist(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_path = _write_workflow(tmp_path, provider="claude", command="claude")

    exit_code = main([str(workflow_path)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "run mode is not implemented yet" in captured.err


def _write_workflow(tmp_path: Path, *, provider: str, command: str) -> Path:
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        f"""---
tracker:
  kind: jira
  jql: project = DEMO
agent:
  provider: {provider}
{provider}:
  command: {command}
---
Work on {{{{ issue.identifier }}}}.
""",
        encoding="utf-8",
    )
    return workflow_path
