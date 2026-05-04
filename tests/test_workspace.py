from __future__ import annotations

import io
from pathlib import Path

import pytest

from synphony.config import SynphonyConfig
from synphony.errors import WorkspaceHookError, WorkspacePathError
from synphony.logging import configure_logging
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


def test_workspace_manager_rejects_non_directory_workspace_collision(tmp_path: Path) -> None:
    (tmp_path / "demo-1").write_text("not a directory", encoding="utf-8")
    manager = WorkspaceManager(root=tmp_path)

    with pytest.raises(WorkspacePathError, match="must be a directory"):
        manager.prepare("DEMO-1")

    assert (tmp_path / "demo-1").is_file()


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


def test_workspace_manager_uses_top_level_hook_timeout_config(tmp_path: Path) -> None:
    calls: list[tuple[str, float]] = []

    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        calls.append((command, timeout_s))
        return HookResult(command=command, exit_code=0, stdout="", stderr="")

    config = SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira", "jql": "project = DEMO"},
            "agent": {"provider": "codex"},
            "codex": {"command": "codex app-server"},
            "hooks": {"before_run": "echo before", "timeout_ms": 1500},
        }
    )
    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(before_run=config.hook_before_run),
        runner=runner,
        hook_timeout_s=config.hook_timeout_s,
    )

    manager.run_before_run(manager.prepare("DEMO-1"))

    assert calls == [("echo before", 1.5)]


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


def test_workspace_manager_cleans_up_after_create_failure(tmp_path: Path) -> None:
    calls: list[str] = []

    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        calls.append(command)
        if command == "after-create":
            return HookResult(command=command, exit_code=2, stdout="", stderr="boom")
        return HookResult(command=command, exit_code=0, stdout="", stderr="")

    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(after_create="after-create", before_remove="before-remove"),
        runner=runner,
    )

    with pytest.raises(WorkspaceHookError):
        manager.prepare("DEMO-1")

    assert calls == ["after-create", "before-remove"]
    assert not (tmp_path / "demo-1").exists()


def test_workspace_manager_ignores_after_run_hook_failures(
    tmp_path: Path,
) -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        return HookResult(command=command, exit_code=2, stdout="", stderr="boom")

    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(after_run="after-run"),
        runner=runner,
    )
    workspace = manager.prepare("DEMO-1")

    manager.run_after_run(workspace)

    assert "workspace hook failed; ignoring" in stream.getvalue()


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


def test_workspace_manager_ignores_before_remove_hook_failures(
    tmp_path: Path,
) -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    def runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        return HookResult(command=command, exit_code=2, stdout="", stderr="boom")

    manager = WorkspaceManager(
        root=tmp_path,
        hooks=WorkspaceHooks(before_remove="before-remove"),
        runner=runner,
    )
    workspace = manager.prepare("DEMO-1")

    assert manager.remove(workspace) is True

    assert not Path(workspace.path).exists()
    assert "workspace hook failed; ignoring" in stream.getvalue()


def test_workspace_manager_cleanup_removes_known_terminal_workspace_keys(tmp_path: Path) -> None:
    manager = WorkspaceManager(root=tmp_path)
    terminal = manager.prepare("DEMO-1")
    active = manager.prepare("DEMO-2")

    removed = manager.cleanup_terminal_workspaces(["DEMO-1"])

    assert removed == [terminal.path]
    assert not Path(terminal.path).exists()
    assert Path(active.path).exists()


def test_workspace_manager_preflights_exact_agent_launch_cwd(tmp_path: Path) -> None:
    manager = WorkspaceManager(root=tmp_path)
    workspace = manager.prepare("DEMO-1")

    manager.preflight_agent_launch(workspace, cwd=Path(workspace.path))

    with pytest.raises(WorkspacePathError, match="exact workspace path"):
        manager.preflight_agent_launch(workspace, cwd=tmp_path)


def test_workspace_manager_preflight_rejects_workspace_path_outside_root(tmp_path: Path) -> None:
    manager = WorkspaceManager(root=tmp_path)
    workspace = manager.prepare("DEMO-1")
    escaped = type(workspace)(
        path=str(tmp_path.parent / "demo-1"),
        key=workspace.key,
        created_now=False,
    )

    with pytest.raises(WorkspacePathError, match="does not match configured root"):
        manager.preflight_agent_launch(escaped, cwd=Path(escaped.path))
