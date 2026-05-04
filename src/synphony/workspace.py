"""Workspace creation, hook execution, and cleanup."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from synphony.errors import WorkspaceHookError
from synphony.models import Workspace, workspace_key_from_identifier
from synphony.path_safety import reject_path_traversal, safe_child_path


@dataclass(frozen=True, slots=True)
class HookResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class WorkspaceHooks:
    after_create: str | None = None
    before_run: str | None = None
    after_run: str | None = None
    before_remove: str | None = None


HookRunner = Callable[[str, Path, float], HookResult]


class WorkspaceManager:
    """Manage deterministic per-issue workspaces under a single safe root."""

    def __init__(
        self,
        *,
        root: str | Path,
        hooks: WorkspaceHooks | None = None,
        runner: HookRunner | None = None,
        hook_timeout_s: float = 30,
        hook_shell: tuple[str, str] = ("sh", "-lc"),
    ) -> None:
        self._root = Path(root).expanduser()
        self._hooks = hooks or WorkspaceHooks()
        self._runner = runner or self._build_subprocess_runner(hook_shell)
        self._hook_timeout_s = hook_timeout_s

    @property
    def root(self) -> Path:
        return self._root

    def prepare(self, issue_identifier: str) -> Workspace:
        reject_path_traversal(issue_identifier)
        key = workspace_key_from_identifier(issue_identifier)
        path = safe_child_path(self._root, key)
        created_now = not path.exists()
        path.mkdir(parents=True, exist_ok=True)

        workspace = Workspace(path=str(path), key=key, created_now=created_now)
        if created_now:
            self._run_hook(self._hooks.after_create, workspace)
        return workspace

    def run_before_run(self, workspace: Workspace) -> None:
        self._run_hook(self._hooks.before_run, workspace)

    def run_after_run(self, workspace: Workspace) -> None:
        self._run_hook(self._hooks.after_run, workspace)

    def remove(self, workspace: Workspace) -> bool:
        path = safe_child_path(self._root, workspace.key)
        if not path.exists():
            return False

        self._run_hook(self._hooks.before_remove, workspace)
        shutil.rmtree(path, ignore_errors=True)
        return not path.exists()

    def cleanup_terminal_workspaces(self, issue_identifiers: Iterable[str]) -> list[str]:
        removed: list[str] = []
        for identifier in issue_identifiers:
            workspace = Workspace(
                path=str(safe_child_path(self._root, workspace_key_from_identifier(identifier))),
                key=workspace_key_from_identifier(identifier),
                created_now=False,
            )
            if self.remove(workspace):
                removed.append(workspace.path)
        return removed

    def _run_hook(self, command: str | None, workspace: Workspace) -> None:
        if command is None:
            return

        path = safe_child_path(self._root, workspace.key)
        try:
            result = self._runner(command, path, self._hook_timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceHookError(
                "workspace hook timed out",
                details={"command": command, "path": str(path), "timeout_s": self._hook_timeout_s},
            ) from exc

        if result.exit_code != 0:
            raise WorkspaceHookError(
                "workspace hook failed",
                details={
                    "command": command,
                    "path": str(path),
                    "exit_code": result.exit_code,
                    "stderr": result.stderr,
                },
            )

    @staticmethod
    def _build_subprocess_runner(hook_shell: tuple[str, str]) -> HookRunner:
        def run(command: str, cwd: Path, timeout_s: float) -> HookResult:
            completed = subprocess.run(
                [hook_shell[0], hook_shell[1], command],
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
            return HookResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

        return run
