from datetime import UTC, datetime

from synphony.errors import (
    AcliNotFoundError,
    AgentTimeoutError,
    JiraQueryFailedError,
    SynphonyError,
)
from synphony.models import (
    AgentEvent,
    AgentUsage,
    Issue,
    LiveSession,
    RetryEntry,
    RunAttempt,
    RuntimeState,
    Workspace,
    build_session_id,
    normalize_state_name,
    workspace_key_from_identifier,
)


def test_workspace_key_from_identifier_is_filesystem_safe() -> None:
    assert workspace_key_from_identifier("PROJ-123") == "proj-123"
    assert workspace_key_from_identifier("Team / Weird Ticket!") == "team-weird-ticket"
    assert workspace_key_from_identifier("___") == "issue"


def test_normalize_state_name_is_case_and_space_insensitive() -> None:
    assert normalize_state_name("  In Progress  ") == "in progress"


def test_build_session_id_includes_provider_and_available_ids() -> None:
    assert build_session_id(provider="codex", thread_id="thread-1", turn_id="turn-2") == (
        "codex:thread-1:turn-2"
    )
    assert build_session_id(provider="claude", thread_id=None, turn_id="turn-9") == (
        "claude:turn-9"
    )


def test_models_capture_representative_runtime_state() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    issue = Issue(
        id="10001",
        identifier="PROJ-123",
        title="Build the thing",
        state="Ready",
        created_at=now,
        updated_at=now,
        priority=1,
        blocked_by=("PROJ-100",),
    )
    workspace = Workspace(path="/tmp/synphony/proj-123", key="proj-123", created_now=True)
    attempt = RunAttempt(issue_id=issue.id, issue_identifier=issue.identifier, attempt=1)
    event = AgentEvent(
        provider="codex",
        session_id="codex:thread-1:turn-1",
        kind="turn.completed",
        occurred_at=now,
        turn_id="turn-1",
        usage=AgentUsage(input_tokens=10, output_tokens=20),
    )
    live = LiveSession(
        issue=issue,
        workspace=workspace,
        attempt=attempt,
        provider="codex",
        session_id=event.session_id,
        started_at=now,
        last_event_at=event.occurred_at,
    )
    retry = RetryEntry(
        issue=issue,
        attempt=attempt,
        next_retry_at=now,
        reason="agent_timeout",
        backoff_ms=1000,
    )
    state = RuntimeState(claimed_issue_ids={issue.id}, running={issue.id: live}, retries=[retry])

    assert issue.normalized_state == "ready"
    assert issue.is_blocked is True
    assert state.running[issue.id].workspace == workspace
    assert state.retries[0].reason == "agent_timeout"


def test_errors_carry_stable_codes_and_details() -> None:
    error = JiraQueryFailedError("JQL failed", details={"status": 2})

    assert isinstance(error, SynphonyError)
    assert error.code == "jira_query_failed"
    assert error.details == {"status": 2}
    assert AcliNotFoundError().code == "acli_not_found"
    assert AgentTimeoutError(provider="claude", timeout_ms=5000).details == {
        "provider": "claude",
        "timeout_ms": 5000,
    }
