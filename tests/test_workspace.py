from __future__ import annotations

from pathlib import Path

import pytest

from synphony.errors import WorkspaceHookError, WorkspacePathError
from synphony.workspace import HookResult, WorkspaceHooks, WorkspaceManager


def test_workspace_manager_creates_deterministic_safe_issue_workspace(tmp_path: Path) -> None:
    manager = WorkspaceManager(root=tmp_path)

    workspace = manager.prepare("DEMO-123")

    assert workspace.key == "demo-123"
    assert Path(workspace.path) == tmp_path / "demo-123"
    assert Path(workspace.path).is_dir()
    assert workspace.created_now is True

    reused = manager.prepare("DEMO-123")

    assert reused.path == workspace.path
    assert reused.created_now is False


def test_workspace_manager_rejects_paths_that_escape_root(tmp_path: Path) -> None:
    manager = WorkspaceManager(root=tmp_path)

    with pytest.raises(WorkspacePathError):
        manager.prepare("../outside")


def test_workspace_manager_runs_after_create_only_for_new_workspace(tmp_path: Path) -> None:
    calls: list[tuple[str, str, float]] = []

    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        calls.append((command, str(cwd), timeout_s))
        return HookResult(command=command, exit_code=0, stdout="ok", stderr="")

    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(after_create="echo created", before_run="echo before"),
        runner=runner,
        hook_timeout_s=4,
    )

    workspace = manager.prepare("DEMO-1")
    manager.run_before_run(workspace)
    manager.prepare("DEMO-1")

    assert calls == [
        ("echo created", str(tmp_path / "demo-1"), 4),
        ("echo before", str(tmp_path / "demo-1"), 4),
    ]


def test_workspace_manager_maps_hook_failures(tmp_path: Path) -> None:
    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        return HookResult(command=command, exit_code=2, stdout="", stderr="boom")

    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(before_run="false"),
        runner=runner,
    )
    workspace = manager.prepare("DEMO-1")

    with pytest.raises(WorkspaceHookError) as exc_info:
        manager.run_before_run(workspace)

    assert exc_info.value.details["exit_code"] == 2


def test_workspace_manager_removes_terminal_workspaces_with_before_remove_hook(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        calls.append(f"{command}:{cwd.name}")
        return HookResult(command=command, exit_code=0, stdout="", stderr="")

    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(before_remove="echo remove"),
        runner=runner,
    )
    workspace = manager.prepare("DEMO-1")

    removed = manager.remove(workspace)

    assert removed is True
    assert calls == ["echo remove:demo-1"]
    assert not Path(workspace.path).exists()


def test_workspace_manager_cleanup_removes_known_terminal_workspace_keys(tmp_path: Path) -> None:
    manager = WorkspaceManager(root=tmp_path)
    terminal = manager.prepare("DEMO-1")
    active = manager.prepare("DEMO-2")

    removed = manager.cleanup_terminal_workspaces(["DEMO-1"])

    assert removed == [terminal.path]
    assert not Path(terminal.path).exists()
    assert Path(active.path).exists()
