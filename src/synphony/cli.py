"""Command-line entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from synphony.config import SynphonyConfig
from synphony.errors import SynphonyError
from synphony.logging import configure_logging, get_logger
from synphony.workflow import load_workflow


def main(argv: Sequence[str] | None = None) -> int:
    """Run the synphony CLI."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    log_path = configure_logging(logs_root=args.logs_root)
    logger = get_logger("cli")

    try:
        workflow = load_workflow(args.workflow)
        config = SynphonyConfig.from_mapping(workflow.config)
    except SynphonyError as exc:
        logger.error(
            "startup validation failed",
            extra={"error_code": exc.code},
        )
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 1

    logger.info(
        "workflow validated",
        extra={"provider": config.agent_provider, "workspace_path": config.workspace_root},
    )

    if args.check:
        suffix = f" logs={log_path}" if log_path is not None else ""
        print(f"workflow ok: {workflow.path}{suffix}")
        return 0

    print(
        "synphony run mode is not implemented yet; use --check for workflow validation",
        file=sys.stderr,
    )
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="synphony")
    parser.add_argument(
        "workflow",
        nargs="?",
        default="./WORKFLOW.md",
        help="Path to WORKFLOW.md (default: ./WORKFLOW.md)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate workflow/config and exit without starting the orchestrator",
    )
    parser.add_argument(
        "--logs-root",
        help="Directory for structured file logs",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Reserved for the optional HTTP status surface",
    )
    return parser
