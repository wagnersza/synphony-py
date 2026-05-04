from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from synphony.agent_runner import AgentRunner
from synphony.agents.base import AgentTurnResult
from synphony.config import SynphonyConfig
from synphony.models import Issue, LiveSession, RunAttempt, Workspace
from synphony.orchestrator import Orchestrator
from synphony.tracker.memory import MemoryTracker
from synphony.workspace import WorkspaceManager
from tests.fakes import FakeAgentBackend


def _issue(
    identifier: str,
    *,
    state: str = "Ready",
    priority: int | None = None,
    created_offset: int = 0,
    blocked_by: tuple[str, ...] = (),
) -> Issue:
    base = datetime(2026, 5, 4, tzinfo=UTC)
    return Issue(
        id=identifier,
        identifier=identifier,
        title=f"Build {identifier}",
        state=state,
        created_at=base + timedelta(minutes=created_offset),
        updated_at=base,
        priority=priority,
        blocked_by=blocked_by,
    )


def _config(tmp_path: Path, *, stall_timeout_ms: int = 60_000) -> SynphonyConfig:
    return SynphonyConfig.from_mapping(
        {
            "tracker": {"kind": "jira"},
            "workflow": {
                "active_states": ["Ready", "In Progress"],
                "terminal_states": ["Done"],
            },
            "agent": {
                "provider": "codex",
                "max_turns": 1,
                "max_concurrent_agents": 2,
                "max_concurrent_agents_by_state": {"Ready": 1},
                "stall_timeout_ms": stall_timeout_ms,
            },
            "codex": {"command": "codex app-server"},
            "workspace": {"root": str(tmp_path / "workspaces")},
        }
    )


def _orchestrator(
    tmp_path: Path,
    tracker: MemoryTracker,
    backend: FakeAgentBackend,
    *,
    config: SynphonyConfig | None = None,
) -> Orchestrator:
    actual_config = config or _config(tmp_path)
    workspace_manager = WorkspaceManager(actual_config)
    runner = AgentRunner(
        config=actual_config,
        workflow_prompt_template="Work on {{ issue.identifier }}.",
        tracker=tracker,
        workspace_manager=workspace_manager,
        backend=backend,
    )
    return Orchestrator(
        config=actual_config,
        tracker=tracker,
        runner=runner,
        workspace_manager=workspace_manager,
    )


def test_orchestrator_claims_dispatchable_issues_by_priority_created_and_identifier(
    tmp_path: Path,
) -> None:
    low_priority = _issue("DEMO-3", priority=5, created_offset=0)
    higher_priority_later = _issue("DEMO-2", priority=0, created_offset=5)
    in_progress = _issue("DEMO-1", state="In Progress", priority=1, created_offset=1)
    blocked = _issue("DEMO-4", priority=-1, blocked_by=("DEMO-0",))
    tracker = MemoryTracker([low_priority, higher_priority_later, in_progress, blocked])
    orchestrator = _orchestrator(tmp_path, tracker, FakeAgentBackend())

    claimed = orchestrator.claim_dispatchable_issues(now=datetime(2026, 5, 4, tzinfo=UTC))

    assert [issue.identifier for issue in claimed] == ["DEMO-2", "DEMO-1"]
    assert orchestrator.state.claimed_issue_ids == {"DEMO-2", "DEMO-1"}


def test_orchestrator_reconciles_terminal_sessions_and_cleans_workspace(tmp_path: Path) -> None:
    issue = _issue("DEMO-1", state="Ready")
    tracker = MemoryTracker([issue])
    backend = FakeAgentBackend(results=[AgentTurnResult(session_id="codex:session-1")])
    orchestrator = _orchestrator(tmp_path, tracker, backend)
    workspace = orchestrator.workspace_manager.prepare_workspace(issue)
    Path(workspace.path, "marker.txt").write_text("created", encoding="utf-8")
    live = LiveSession(
        issue=issue,
        workspace=workspace,
        attempt=RunAttempt(issue_id=issue.id, issue_identifier=issue.identifier, attempt=1),
        provider="codex",
        session_id="codex:session-1",
        started_at=datetime(2026, 5, 4, tzinfo=UTC),
        last_event_at=datetime(2026, 5, 4, tzinfo=UTC),
    )
    orchestrator.state.running[issue.id] = live
    orchestrator.state.claimed_issue_ids.add(issue.id)
    tracker.set_issue_state(issue.id, "Done")

    orchestrator.reconcile(now=datetime(2026, 5, 4, 0, 1, tzinfo=UTC))

    assert issue.id not in orchestrator.state.running
    assert issue.id not in orchestrator.state.claimed_issue_ids
    assert not Path(workspace.path).exists()
    assert backend.stopped_sessions == [("codex:session-1", Path(workspace.path))]


def test_orchestrator_moves_stalled_sessions_to_retry(tmp_path: Path) -> None:
    issue = _issue("DEMO-1", state="Ready")
    tracker = MemoryTracker([issue])
    config = _config(tmp_path, stall_timeout_ms=1_000)
    backend = FakeAgentBackend(results=[AgentTurnResult(session_id="codex:session-1")])
    orchestrator = _orchestrator(tmp_path, tracker, backend, config=config)
    workspace = Workspace(
        path=str(tmp_path / "workspaces" / "demo-1"), key="demo-1", created_now=False
    )
    now = datetime(2026, 5, 4, tzinfo=UTC)
    live = LiveSession(
        issue=issue,
        workspace=workspace,
        attempt=RunAttempt(issue_id=issue.id, issue_identifier=issue.identifier, attempt=1),
        provider="codex",
        session_id="codex:session-1",
        started_at=now - timedelta(seconds=10),
        last_event_at=now - timedelta(seconds=10),
    )
    orchestrator.state.running[issue.id] = live
    orchestrator.state.claimed_issue_ids.add(issue.id)

    orchestrator.reconcile(now=now)

    assert issue.id not in orchestrator.state.running
    assert orchestrator.state.retries[0].issue == issue
    assert orchestrator.state.retries[0].reason == "agent_stalled"


def test_orchestrator_startup_cleanup_removes_terminal_workspaces(tmp_path: Path) -> None:
    done_issue = _issue("DEMO-1", state="Done")
    tracker = MemoryTracker([done_issue])
    orchestrator = _orchestrator(tmp_path, tracker, FakeAgentBackend())
    workspace = orchestrator.workspace_manager.prepare_workspace(done_issue)
    Path(workspace.path, "marker.txt").write_text("created", encoding="utf-8")

    orchestrator.cleanup_terminal_workspaces()

    assert not Path(workspace.path).exists()
