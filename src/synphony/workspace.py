"""Workspace path safety, lifecycle creation, hooks, and cleanup."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from synphony.config import SynphonyConfig
from synphony.errors import SynphonyError
from synphony.models import Issue, Workspace


class WorkspaceError(SynphonyError):
    code = "workspace_error"


class WorkspaceHookError(WorkspaceError):
    code = "workspace_hook_failed"


class WorkspaceManager:
    def __init__(self, config: SynphonyConfig) -> None:
        self._config = config
        self._root = Path(config.workspace_root).resolve()

    @property
    def root(self) -> Path:
        return self._root

    def workspace_for_issue(self, issue: Issue) -> Workspace:
        path = self._safe_workspace_path(issue)
        return Workspace(path=str(path), key=issue.workspace_key, created_now=False)

    def prepare_workspace(self, issue: Issue) -> Workspace:
        path = self._safe_workspace_path(issue)
        created_now = not path.exists()
        path.mkdir(parents=True, exist_ok=True)
        return Workspace(path=str(path), key=issue.workspace_key, created_now=created_now)

    def run_hook(self, name: str, workspace: Workspace) -> None:
        command = self._config.workspace_hooks.get(name)
        if command is None:
            return

        try:
            subprocess.run(
                ["sh", "-lc", command],
                cwd=workspace.path,
                timeout=self._config.workspace_hook_timeout_ms / 1000,
                check=True,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkspaceHookError(
                f"workspace hook failed: {name}",
                details={"hook": name, "workspace": workspace.path},
            ) from exc

    def cleanup_workspace(self, workspace: Workspace) -> None:
        if Path(workspace.path).exists():
            self.run_hook("before_remove", workspace)
            shutil.rmtree(workspace.path)

    def _safe_workspace_path(self, issue: Issue) -> Path:
        path = (self._root / issue.workspace_key).resolve()
        try:
            path.relative_to(self._root)
        except ValueError as exc:
            raise WorkspaceError(
                "workspace path escapes configured root",
                details={"root": str(self._root), "path": str(path)},
            ) from exc
        return path
