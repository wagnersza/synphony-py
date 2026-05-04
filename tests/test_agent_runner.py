from __future__ import annotations

from pathlib import Path

from synphony.agent_runner import AgentRunner
from synphony.agents.base import AgentTurnResult
from synphony.config import SynphonyConfig
from synphony.models import AgentEvent, Issue
from synphony.tracker.memory import MemoryTracker
from synphony.workspace import WorkspaceManager
from tests.fakes import FakeAgentBackend


def _config(tmp_path: Path, *, max_turns: int = 2) -> SynphonyConfig:
    hooks_log = tmp_path / "hooks.log"
    return SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira"},
            "workflow": {"active_states": ["Ready"], "terminal_states": ["Done"]},
            "agent": {"provider": "codex", "max_turns": max_turns},
            "codex": {"command": "codex app-server"},
            "workspace": {
                "root": str(tmp_path / "workspaces"),
                "hooks": {
                    "after_create": f"printf 'after_create\\n' >> {hooks_log}",
                    "before_run": f"printf 'before_run\\n' >> {hooks_log}",
                    "after_run": f"printf 'after_run\\n' >> {hooks_log}",
                },
            },
        }
    )


def test_agent_runner_builds_prompts_runs_hooks_and_forwards_events(
    tmp_path: Path, make_issue: Issue
) -> None:
    config = _config(tmp_path)
    tracker = MemoryTracker([make_issue])
    backend = FakeAgentBackend(
        results=[
            AgentTurnResult(session_id="codex:session-1", completed=False),
            AgentTurnResult(session_id="codex:session-1", completed=True),
        ]
    )
    runner = AgentRunner(
        config=config,
        workflow_prompt_template="Work on {{ issue.identifier }} attempt {{ attempt.number }}.",
        tracker=tracker,
        workspace_manager=WorkspaceManager(config),
        backend=backend,
    )
    events: list[AgentEvent] = []

    outcome = runner.run(make_issue, attempt_number=1, on_event=events.append)

    assert outcome.session_id == "codex:session-1"
    assert outcome.stop_reason == "completed"
    assert [request.turn_number for request in backend.requests] == [1, 2]
    assert backend.requests[0].prompt == "Work on DEMO-1 attempt 1."
    assert backend.requests[1].prompt.startswith("Continue work on DEMO-1")
    assert [event.kind for event in events] == ["turn.awaiting_continuation", "turn.completed"]
    assert (tmp_path / "hooks.log").read_text(encoding="utf-8").splitlines() == [
        "after_create",
        "before_run",
        "after_run",
        "before_run",
        "after_run",
    ]


def test_agent_runner_stops_before_continuation_when_issue_becomes_inactive(
    tmp_path: Path, make_issue: Issue
) -> None:
    config = _config(tmp_path, max_turns=3)
    tracker = MemoryTracker([make_issue])

    def mark_done(_: object) -> None:
        tracker.set_issue_state(make_issue.id, "Done")

    backend = FakeAgentBackend(
        results=[AgentTurnResult(session_id="codex:session-1", completed=False)],
        after_turn=mark_done,
    )
    runner = AgentRunner(
        config=config,
        workflow_prompt_template="Work on {{ issue.identifier }}.",
        tracker=tracker,
        workspace_manager=WorkspaceManager(config),
        backend=backend,
    )

    outcome = runner.run(make_issue, attempt_number=1, on_event=lambda _: None)

    assert outcome.stop_reason == "issue_inactive"
    assert len(backend.requests) == 1
