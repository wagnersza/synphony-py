"""Command-line entrypoint for the synphony daemon."""

from __future__ import annotations

import argparse
import logging as stdlib_logging
import signal
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from types import FrameType
from typing import Protocol, cast

from synphony.agent_runner import AgentRunner
from synphony.agents.registry import create_default_registry
from synphony.config import SynphonyConfig
from synphony.errors import SynphonyError
from synphony.http import StatusServer
from synphony.logging import configure_logging
from synphony.models import AgentEvent, WorkflowDefinition
from synphony.orchestrator import Orchestrator
from synphony.tracker.jira_acli import JiraAcliTracker
from synphony.workflow import load_workflow
from synphony.workspace import WorkspaceManager

SignalHandler = Callable[[int, FrameType | None], object]


class RuntimeApp(Protocol):
    def run(self, stop_event: Event) -> int:
        """Run until complete or until `stop_event` requests shutdown."""


class AppFactory(Protocol):
    def __call__(
        self,
        workflow: WorkflowDefinition,
        config: SynphonyConfig,
        *,
        port: int | None,
    ) -> RuntimeApp:
        """Build a runtime app after startup validation succeeds."""


class SynphonyRuntimeApp:
    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        config: SynphonyConfig,
        logger: stdlib_logging.Logger,
        port: int | None,
    ) -> None:
        self._orchestrator = orchestrator
        self._config = config
        self._logger = logger
        self._port = port

    def run(self, stop_event: Event) -> int:
        server = self._start_http_server() if self._port is not None else None
        try:
            self._logger.info("synphony daemon starting")
            self._orchestrator.cleanup_terminal_workspaces()
            while not stop_event.is_set():
                self._orchestrator.run_once(
                    now=datetime.now(UTC),
                    on_event=self._log_agent_event,
                )
                stop_event.wait(self._config.polling_interval_ms / 1000)
            self._logger.info("synphony daemon stopping")
            return 0
        finally:
            if server is not None:
                server.stop()

    def _start_http_server(self) -> StatusServer:
        assert self._port is not None
        server = StatusServer(state=self._orchestrator.state, port=self._port)
        server.start()
        self._logger.info("status server started", extra={"port": server.port})
        return server

    def _log_agent_event(self, event: AgentEvent) -> None:
        self._logger.info(
            event.kind,
            extra={
                "provider": event.provider,
                "session_id": event.session_id,
            },
        )


def run(
    argv: Sequence[str] | None = None,
    *,
    app_factory: AppFactory | None = None,
) -> int:
    args = _parse_args(argv)
    logger = configure_logging(args.logs_root)
    try:
        workflow = load_workflow(args.workflow_path.resolve())
        config = SynphonyConfig.from_mapping(workflow.config)
        factory = app_factory or build_runtime_app
        stop_event = Event()
        previous_handlers = _install_signal_handlers(stop_event)
        try:
            app = factory(workflow, config, port=args.port)
            return app.run(stop_event)
        finally:
            _restore_signal_handlers(previous_handlers)
    except SynphonyError as exc:
        logger.error("startup validation failed", extra={"error": exc})
        return 2


def build_runtime_app(
    workflow: WorkflowDefinition,
    config: SynphonyConfig,
    *,
    port: int | None,
) -> RuntimeApp:
    tracker = JiraAcliTracker(
        jql=config.tracker_jql or "",
        active_state_names=config.active_states,
    )
    workspace_manager = WorkspaceManager(config)
    backend = create_default_registry(config).get(config.agent_provider)
    runner = AgentRunner(
        config=config,
        workflow_prompt_template=workflow.prompt_template,
        tracker=tracker,
        workspace_manager=workspace_manager,
        backend=backend,
    )
    orchestrator = Orchestrator(
        config=config,
        tracker=tracker,
        runner=runner,
        workspace_manager=workspace_manager,
    )
    return SynphonyRuntimeApp(
        orchestrator=orchestrator,
        config=config,
        logger=stdlib_logging.getLogger("synphony"),
        port=port,
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="synphony")
    parser.add_argument(
        "workflow_path",
        nargs="?",
        default=Path("WORKFLOW.md"),
        type=Path,
        help="Path to a WORKFLOW.md file. Defaults to ./WORKFLOW.md.",
    )
    parser.add_argument("--logs-root", type=Path, default=None)
    parser.add_argument("--port", type=int, default=None)
    return parser.parse_args(argv)


def _install_signal_handlers(stop_event: Event) -> dict[int, signal.Handlers]:
    previous: dict[int, signal.Handlers] = {}

    def request_stop(signum: int, frame: FrameType | None) -> None:
        stop_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = cast(signal.Handlers, signal.signal(signum, request_stop))
    return previous


def _restore_signal_handlers(previous: dict[int, signal.Handlers]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)
