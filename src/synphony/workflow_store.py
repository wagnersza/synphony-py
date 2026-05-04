"""Reloadable workflow store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from synphony.errors import SynphonyError
from synphony.models import WorkflowDefinition
from synphony.workflow import load_workflow


@dataclass(frozen=True, slots=True)
class WorkflowReloadResult:
    workflow: WorkflowDefinition | None
    changed: bool
    error: SynphonyError | None = None


class WorkflowStore:
    """Load a workflow file and keep the last good version across invalid reloads."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._workflow: WorkflowDefinition | None = None
        self._signature: tuple[int, int] | None = None

    @property
    def workflow(self) -> WorkflowDefinition | None:
        return self._workflow

    def load(self) -> WorkflowReloadResult:
        workflow = load_workflow(self._path)
        self._workflow = workflow
        self._signature = self._file_signature()
        return WorkflowReloadResult(workflow=workflow, changed=True)

    def reload_if_changed(self) -> WorkflowReloadResult:
        signature = self._file_signature()
        if self._workflow is not None and signature == self._signature:
            return WorkflowReloadResult(workflow=self._workflow, changed=False)

        try:
            workflow = load_workflow(self._path)
        except SynphonyError as exc:
            return WorkflowReloadResult(workflow=self._workflow, changed=False, error=exc)

        self._workflow = workflow
        self._signature = signature
        return WorkflowReloadResult(workflow=workflow, changed=True)

    def _file_signature(self) -> tuple[int, int]:
        stat = self._path.stat()
        return stat.st_mtime_ns, stat.st_size
