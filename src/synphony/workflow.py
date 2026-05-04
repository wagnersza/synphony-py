"""Workflow file loading."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from synphony.errors import WorkflowNotFoundError, WorkflowParseError
from synphony.models import WorkflowDefinition


def load_workflow(path: str | Path) -> WorkflowDefinition:
    workflow_path = Path(path)
    if not workflow_path.exists():
        raise WorkflowNotFoundError(f"workflow file not found: {workflow_path}")

    text = workflow_path.read_text(encoding="utf-8")
    config, prompt_template = _split_front_matter(text)
    return WorkflowDefinition(
        path=str(workflow_path),
        config=config,
        prompt_template=prompt_template,
        loaded_at=datetime.now(UTC),
    )


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text.strip()

    try:
        _, yaml_text, body = text.split("---", 2)
    except ValueError as exc:
        raise WorkflowParseError("workflow front matter must be closed with ---") from exc

    try:
        parsed = yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise WorkflowParseError("workflow front matter is invalid YAML") from exc

    if not isinstance(parsed, dict):
        raise WorkflowParseError("workflow front matter must be a YAML mapping")

    return parsed, body.strip()
