"""Workspace creation, hook execution, and cleanup."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from synphony.errors import WorkspaceHookError, WorkspacePathError
from synphony.logging import get_logger
from synphony.models import Workspace, workspace_key_from_identifier
from synphony.path_safety import reject_path_traversal, safe_child_path

_LOGGER = get_logger("workspace")


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
        self._root = Path(root).expanduser().resolve()
        self._hooks = hooks or WorkspaceHooks()
        self._runner = runner or self._build_subprocess_runner(hook_shell)
        self._hook_timeout_s = hook_timeout_s

    @property
    def root(self) -> Path:
        return self._root

    def prepare(self, issue_identifier: str) -> Workspace:
        reject_path_traversal(issue_identifier)
        key = workspace_key_from_identifier(issue_identifier)
        self._ensure_root_is_directory()
        path = safe_child_path(self._root, key)
        created_now = not path.exists()
        if path.exists() and not path.is_dir():
            raise WorkspacePathError(
                "workspace path must be a directory",
                details={"path": str(path), "root": str(self._root)},
            )
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WorkspacePathError(
                "workspace path could not be created",
                details={"path": str(path), "root": str(self._root)},
            ) from exc

        workspace = Workspace(path=str(path), key=key, created_now=created_now)
        if created_now:
            try:
                self._run_required_hook(self._hooks.after_create, workspace)
            except WorkspaceHookError:
                self.remove(workspace)
                raise
        return workspace

    def run_before_run(self, workspace: Workspace) -> None:
        self._run_required_hook(self._hooks.before_run, workspace)

    def run_after_run(self, workspace: Workspace) -> None:
        self._run_best_effort_hook(self._hooks.after_run, workspace)

    def remove(self, workspace: Workspace) -> bool:
        path = safe_child_path(self._root, workspace.key)
        if not path.exists():
            return False

        self._run_best_effort_hook(self._hooks.before_remove, workspace)
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

    def preflight_agent_launch(self, workspace: Workspace, *, cwd: str | Path) -> None:
        """Validate the launch cwd is exactly the prepared workspace under root."""
        expected_path = safe_child_path(self._root, workspace.key)
        workspace_path = Path(workspace.path).expanduser().resolve()
        if workspace_path != expected_path:
            raise WorkspacePathError(
                "workspace path does not match configured root",
                details={
                    "root": str(self._root),
                    "expected_path": str(expected_path),
                    "workspace_path": str(workspace_path),
                },
            )
        if not workspace_path.is_dir():
            raise WorkspacePathError(
                "workspace path must be a directory",
                details={"path": str(workspace_path), "root": str(self._root)},
            )

        cwd_path = Path(cwd).expanduser().resolve()
        if cwd_path != workspace_path:
            raise WorkspacePathError(
                "agent launch cwd must be the exact workspace path",
                details={"cwd": str(cwd_path), "workspace_path": str(workspace_path)},
            )

    def _ensure_root_is_directory(self) -> None:
        if self._root.exists() and not self._root.is_dir():
            raise WorkspacePathError(
                "workspace root must be a directory",
                details={"root": str(self._root)},
            )

    def _run_required_hook(self, command: str | None, workspace: Workspace) -> None:
        self._run_hook(command, workspace)

    def _run_best_effort_hook(self, command: str | None, workspace: Workspace) -> None:
        try:
            self._run_hook(command, workspace)
        except WorkspaceHookError as exc:
            _LOGGER.warning(
                "workspace hook failed; ignoring",
                extra={"error_code": exc.code, "workspace_path": exc.details.get("path")},
            )

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
