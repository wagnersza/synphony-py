from __future__ import annotations

from pathlib import Path

from fakes import FakeAgentBackend

from synphony.agent_runner import AgentRunConfig, AgentRunner, StopReason
from synphony.models import Issue, RunAttempt, Workspace
from synphony.workspace import HookResult, WorkspaceHooks, WorkspaceManager


def test_runner_renders_first_prompt_runs_hooks_and_stops_session(
    tmp_path: Path,
    make_issue: Issue,
) -> None:
    hook_calls: list[str] = []

    def hook_runner(command: str, cwd: Path, timeout_s: float) -> HookResult:
        hook_calls.append(f"{command}:{cwd.name}")
        return HookResult(command=command, exit_code=0, stdout="", stderr="")

    backend = FakeAgentBackend(provider="codex")
    runner = AgentRunner(
        backend=backend,
        workspace_manager=WorkspaceManager(
            root=tmp_path,
            hooks=WorkspaceHooks(
                after_create="after-create",
                before_run="before-run",
                after_run="after-run",
            ),
            runner=hook_runner,
        ),
        prompt_template="Work on {{ issue.identifier }} attempt {{ attempt.number }}",
        config=AgentRunConfig(active_state_names=("Ready",)),
        issue_state_fetcher=lambda issue_ids: {issue_id: "Done" for issue_id in issue_ids},
    )

    result = runner.run(make_issue, RunAttempt("10001", "DEMO-1", 2))

    assert result.stop_reason is StopReason.INACTIVE
    assert result.turns_completed == 1
    assert backend.turn_inputs[0].prompt == "Work on DEMO-1 attempt 2"
    assert backend.stopped_sessions == (result.session_id,)
    assert hook_calls == [
        "after-create:demo-1",
        "before-run:demo-1",
        "after-run:demo-1",
    ]


def test_runner_preflights_agent_launch_workspace(
    tmp_path: Path,
    make_issue: Issue,
) -> None:
    class RecordingWorkspaceManager(WorkspaceManager):
        def __init__(self, *, root: Path) -> None:
            super().__init__(root=root)
            self.preflight_calls: list[tuple[str, str]] = []

        def preflight_agent_launch(self, workspace: Workspace, *, cwd: str | Path) -> None:
            self.preflight_calls.append((workspace.path, str(cwd)))
            super().preflight_agent_launch(workspace, cwd=cwd)

    workspace_manager = RecordingWorkspaceManager(root=tmp_path)
    runner = AgentRunner(
        backend=FakeAgentBackend(provider="codex"),
        workspace_manager=workspace_manager,
        prompt_template="Work on {{ issue.identifier }}",
        config=AgentRunConfig(active_state_names=("Ready",)),
        issue_state_fetcher=lambda issue_ids: {issue_id: "Done" for issue_id in issue_ids},
    )

    runner.run(make_issue, RunAttempt("10001", "DEMO-1", 1))

    assert workspace_manager.preflight_calls == [
        (str(tmp_path / "demo-1"), str(tmp_path / "demo-1"))
    ]


def test_runner_uses_continuation_guidance_while_issue_stays_active(
    tmp_path: Path,
    make_issue: Issue,
) -> None:
    states = iter(("Ready", "Done"))
    backend = FakeAgentBackend(provider="codex")
    runner = AgentRunner(
        backend=backend,
        workspace_manager=WorkspaceManager(root=tmp_path),
        prompt_template="Original task: {{ issue.title }}",
        config=AgentRunConfig(active_state_names=("Ready",), max_turns=5),
        issue_state_fetcher=lambda issue_ids: {next(iter(issue_ids)): next(states)},
    )

    result = runner.run(make_issue, RunAttempt("10001", "DEMO-1", 1))

    assert result.stop_reason is StopReason.INACTIVE
    assert result.turns_completed == 2
    assert backend.turn_inputs[0].prompt == "Original task: Add tests"
    assert "Continuation guidance" in backend.turn_inputs[1].prompt
    assert "Original task" not in backend.turn_inputs[1].prompt
    assert backend.turn_inputs[1].session_id == result.session_id


def test_runner_stops_at_max_turns_when_issue_remains_active(
    tmp_path: Path,
    make_issue: Issue,
) -> None:
    backend = FakeAgentBackend(provider="claude")
    runner = AgentRunner(
        backend=backend,
        workspace_manager=WorkspaceManager(root=tmp_path),
        prompt_template="Work on {{ issue.identifier }}",
        config=AgentRunConfig(active_state_names=("Ready",), max_turns=2),
        issue_state_fetcher=lambda issue_ids: {issue_id: "Ready" for issue_id in issue_ids},
    )

    result = runner.run(make_issue, RunAttempt("10001", "DEMO-1", 1))

    assert result.stop_reason is StopReason.MAX_TURNS
    assert result.turns_completed == 2
    assert len(backend.turn_inputs) == 2
    assert backend.stopped_sessions == (result.session_id,)
