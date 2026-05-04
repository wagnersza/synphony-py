from __future__ import annotations

import signal
from collections.abc import Callable
from pathlib import Path
from threading import Event
from types import FrameType

import pytest

from synphony.cli import RuntimeApp, _install_signal_handlers, run
from synphony.config import SynphonyConfig
from synphony.models import WorkflowDefinition


class _FakeApp(RuntimeApp):
    def __init__(self) -> None:
        self.stop_event: Event | None = None

    def run(self, stop_event: Event) -> int:
        self.stop_event = stop_event
        return 0


def test_cli_defaults_to_workflow_md_and_builds_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
Work on {{ issue.identifier }}.
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    created: list[tuple[WorkflowDefinition, SynphonyConfig, int | None]] = []
    app = _FakeApp()

    def app_factory(
        workflow: WorkflowDefinition,
        config: SynphonyConfig,
        *,
        port: int | None,
    ) -> RuntimeApp:
        created.append((workflow, config, port))
        return app

    exit_code = run([], app_factory=app_factory)

    assert exit_code == 0
    assert created[0][0].path == str(workflow_path)
    assert created[0][1].agent_provider == "codex"
    assert created[0][2] is None
    assert app.stop_event is not None


def test_cli_returns_nonzero_for_startup_validation_failure(tmp_path: Path) -> None:
    missing = tmp_path / "missing.md"

    assert run([str(missing)]) == 2


def test_cli_passes_logs_root_and_port(tmp_path: Path) -> None:
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
Prompt
""",
        encoding="utf-8",
    )
    app = _FakeApp()
    ports: list[int | None] = []

    def app_factory(
        workflow: WorkflowDefinition,
        config: SynphonyConfig,
        *,
        port: int | None,
    ) -> RuntimeApp:
        ports.append(port)
        return app

    exit_code = run(
        [str(workflow_path), "--logs-root", str(tmp_path / "logs"), "--port", "8765"],
        app_factory=app_factory,
    )

    assert exit_code == 0
    assert ports == [8765]
    assert (tmp_path / "logs" / "synphony.log").exists()


def test_signal_handlers_request_graceful_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: dict[int, Callable[[int, FrameType | None], None]] = {}

    def fake_signal(
        signum: int,
        handler: Callable[[int, FrameType | None], None],
    ) -> signal.Handlers:
        registered[signum] = handler
        return signal.SIG_DFL

    monkeypatch.setattr(signal, "signal", fake_signal)
    stop_event = Event()

    previous = _install_signal_handlers(stop_event)
    registered[signal.SIGTERM](signal.SIGTERM, None)

    assert stop_event.is_set()
    assert set(previous) == {signal.SIGINT, signal.SIGTERM}
