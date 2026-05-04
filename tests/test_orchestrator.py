from __future__ import annotations

from datetime import UTC, datetime, timedelta

from synphony.models import Issue, LiveSession, RetryEntry, RunAttempt, RuntimeState, Workspace
from synphony.orchestrator import Orchestrator, OrchestratorConfig
from synphony.tracker.memory import MemoryTracker


def test_orchestrator_dispatches_candidates_by_priority_creation_and_identifier() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    issues = [
        _issue("3", "DEMO-3", priority=2, created_at=now),
        _issue("2", "DEMO-2", priority=1, created_at=now + timedelta(seconds=1)),
        _issue("1", "DEMO-1", priority=1, created_at=now),
    ]
    started: list[str] = []
    orchestrator = Orchestrator(
        tracker=MemoryTracker(issues, active_state_names=("Ready",)),
        config=OrchestratorConfig(active_state_names=("Ready",), max_concurrent_agents=2),
        run_starter=lambda issue, attempt: _live_session(issue, attempt, started),
    )

    result = orchestrator.dispatch_once()

    assert [session.issue.identifier for session in result.started] == ["DEMO-1", "DEMO-2"]
    assert started == ["DEMO-1", "DEMO-2"]
    assert set(orchestrator.state.running) == {"1", "2"}
    assert orchestrator.state.claimed_issue_ids == set()


def test_orchestrator_enforces_per_state_concurrency_caps() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    ready_issue = _issue("2", "DEMO-2", state="Ready", priority=1, created_at=now)
    review_issue = _issue("3", "DEMO-3", state="Review", priority=1, created_at=now)
    already_running = _issue("1", "DEMO-1", state="Ready", priority=1, created_at=now)
    state = RuntimeState(
        running={"1": _live_session(already_running, RunAttempt("1", "DEMO-1", 1), [])}
    )
    orchestrator = Orchestrator(
        tracker=MemoryTracker(
            (ready_issue, review_issue),
            active_state_names=("Ready", "Review"),
        ),
        config=OrchestratorConfig(
            active_state_names=("Ready", "Review"),
            max_concurrent_agents=5,
            max_concurrent_agents_by_state={"Ready": 1, "Review": 1},
        ),
        run_starter=lambda issue, attempt: _live_session(issue, attempt, []),
        state=state,
    )

    result = orchestrator.dispatch_once()

    assert [session.issue.identifier for session in result.started] == ["DEMO-3"]
    assert set(orchestrator.state.running) == {"1", "3"}


def test_orchestrator_skips_blocked_running_claimed_and_retrying_issues() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    blocked = _issue("1", "DEMO-1", blocked_by=("DEMO-0",), created_at=now)
    running = _issue("2", "DEMO-2", created_at=now)
    claimed = _issue("3", "DEMO-3", created_at=now)
    retrying = _issue("4", "DEMO-4", created_at=now)
    dispatchable = _issue("5", "DEMO-5", created_at=now)
    state = RuntimeState(
        claimed_issue_ids={"3"},
        running={"2": _live_session(running, RunAttempt("2", "DEMO-2", 1), [])},
        retries=[
            RetryEntry(
                issue=retrying,
                attempt=RunAttempt("4", "DEMO-4", 1),
                next_retry_at=now + timedelta(seconds=30),
                reason="backoff",
                backoff_ms=30_000,
            )
        ],
    )
    orchestrator = Orchestrator(
        tracker=MemoryTracker(
            (blocked, running, claimed, retrying, dispatchable),
            active_state_names=("Ready",),
        ),
        config=OrchestratorConfig(active_state_names=("Ready",), max_concurrent_agents=5),
        run_starter=lambda issue, attempt: _live_session(issue, attempt, []),
        state=state,
    )

    result = orchestrator.dispatch_once()

    assert [session.issue.identifier for session in result.started] == ["DEMO-5"]
    assert set(orchestrator.state.running) == {"2", "5"}
    assert orchestrator.state.claimed_issue_ids == {"3"}


def test_orchestrator_reconciliation_stops_and_cleans_terminal_sessions() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    running_issue = _issue("1", "DEMO-1", state="Ready", created_at=now)
    terminal_issue = _issue("1", "DEMO-1", state="Done", created_at=now)
    stopped: list[str] = []
    cleaned: list[str] = []

    def clean_session(session: LiveSession) -> bool:
        cleaned.append(session.workspace.path)
        return True

    orchestrator = Orchestrator(
        tracker=MemoryTracker((terminal_issue,), active_state_names=("Ready",)),
        config=OrchestratorConfig(
            active_state_names=("Ready",),
            terminal_state_names=("Done",),
        ),
        run_starter=lambda issue, attempt: _live_session(issue, attempt, []),
        session_stopper=lambda session: stopped.append(session.session_id),
        workspace_cleaner=clean_session,
        state=RuntimeState(
            running={"1": _live_session(running_issue, RunAttempt("1", "DEMO-1", 1), [])}
        ),
    )

    result = orchestrator.reconcile_once(now=now)

    assert [session.issue.identifier for session in result.stopped] == ["DEMO-1"]
    assert [session.issue.identifier for session in result.cleaned] == ["DEMO-1"]
    assert stopped == ["fake:1"]
    assert cleaned == ["/tmp/demo-1"]
    assert orchestrator.state.running == {}


def test_orchestrator_reconciliation_stops_inactive_sessions_without_cleanup() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    running_issue = _issue("1", "DEMO-1", state="Ready", created_at=now)
    inactive_issue = _issue("1", "DEMO-1", state="Paused", created_at=now)
    cleaned: list[str] = []

    def clean_session(session: LiveSession) -> bool:
        cleaned.append(session.workspace.path)
        return True

    orchestrator = Orchestrator(
        tracker=MemoryTracker((inactive_issue,), active_state_names=("Ready",)),
        config=OrchestratorConfig(
            active_state_names=("Ready",),
            terminal_state_names=("Done",),
        ),
        run_starter=lambda issue, attempt: _live_session(issue, attempt, []),
        workspace_cleaner=clean_session,
        state=RuntimeState(
            running={"1": _live_session(running_issue, RunAttempt("1", "DEMO-1", 1), [])}
        ),
    )

    result = orchestrator.reconcile_once(now=now)

    assert [session.issue.identifier for session in result.stopped] == ["DEMO-1"]
    assert result.cleaned == ()
    assert cleaned == []
    assert orchestrator.state.running == {}


def test_orchestrator_reconciliation_schedules_retry_for_stalled_sessions() -> None:
    now = datetime(2026, 5, 4, 12, 0, tzinfo=UTC)
    issue = _issue("1", "DEMO-1", state="Ready", created_at=now)
    stale_session = _live_session(issue, RunAttempt("1", "DEMO-1", 1), [])
    stale_session = LiveSession(
        issue=stale_session.issue,
        workspace=stale_session.workspace,
        attempt=stale_session.attempt,
        provider=stale_session.provider,
        session_id=stale_session.session_id,
        started_at=stale_session.started_at,
        last_event_at=now - timedelta(seconds=30),
    )
    stopped: list[str] = []
    orchestrator = Orchestrator(
        tracker=MemoryTracker((issue,), active_state_names=("Ready",)),
        config=OrchestratorConfig(
            active_state_names=("Ready",),
            terminal_state_names=("Done",),
            stall_timeout_s=10,
            retry_base_backoff_ms=1000,
        ),
        run_starter=lambda issue, attempt: _live_session(issue, attempt, []),
        session_stopper=lambda session: stopped.append(session.session_id),
        state=RuntimeState(running={"1": stale_session}),
    )

    result = orchestrator.reconcile_once(now=now)

    assert [entry.issue.identifier for entry in result.retries] == ["DEMO-1"]
    assert stopped == ["fake:1"]
    assert orchestrator.state.running == {}
    assert len(orchestrator.state.retries) == 1
    retry = orchestrator.state.retries[0]
    assert retry.attempt.attempt == 2
    assert retry.next_retry_at == now + timedelta(milliseconds=1000)
    assert retry.reason == "stalled"


def _issue(
    issue_id: str,
    identifier: str,
    *,
    state: str = "Ready",
    priority: int | None = None,
    created_at: datetime,
    blocked_by: tuple[str, ...] = (),
) -> Issue:
    return Issue(
        id=issue_id,
        identifier=identifier,
        title=identifier,
        state=state,
        priority=priority,
        created_at=created_at,
        updated_at=created_at,
        blocked_by=blocked_by,
    )


def _live_session(issue: Issue, attempt: RunAttempt, started: list[str]) -> LiveSession:
    started.append(issue.identifier)
    now = datetime(2026, 5, 4, tzinfo=UTC)
    return LiveSession(
        issue=issue,
        workspace=Workspace(
            path=f"/tmp/{issue.workspace_key}",
            key=issue.workspace_key,
            created_now=True,
        ),
        attempt=attempt,
        provider="fake",
        session_id=f"fake:{issue.id}",
        started_at=now,
        last_event_at=now,
    )
