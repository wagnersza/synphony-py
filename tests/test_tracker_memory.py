from datetime import UTC, datetime, timedelta

from synphony.models import Issue
from synphony.tracker.memory import MemoryTracker


def test_memory_tracker_fetches_active_candidate_issues() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    ready = _issue("10001", "DEMO-1", "Ready", now)
    in_progress = _issue("10002", "DEMO-2", "In Progress", now + timedelta(seconds=1))
    done = _issue("10003", "DEMO-3", "Done", now + timedelta(seconds=2))

    tracker = MemoryTracker(
        [done, in_progress, ready],
        active_state_names=["ready", "in progress"],
        terminal_state_names=["done"],
    )

    assert tracker.fetch_candidate_issues() == [ready, in_progress]


def test_memory_tracker_can_model_blocked_and_priority_cases() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    blocked = _issue("10001", "DEMO-1", "Ready", now, priority=1, blocked_by=("DEMO-0",))
    unblocked = _issue("10002", "DEMO-2", "Ready", now, priority=3)

    tracker = MemoryTracker(
        [unblocked, blocked],
        active_state_names=["ready"],
        terminal_state_names=["done"],
    )

    candidates = tracker.fetch_candidate_issues()

    assert candidates == [blocked, unblocked]
    assert candidates[0].is_blocked is True
    assert candidates[0].priority == 1


def test_memory_tracker_fetches_by_state_names_case_insensitively() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    ready = _issue("10001", "DEMO-1", "Ready", now)
    done = _issue("10002", "DEMO-2", "DONE", now)

    tracker = MemoryTracker([ready, done], active_state_names=["ready"])

    assert tracker.fetch_issues_by_states(["done"]) == [done]


def test_memory_tracker_fetches_issue_states_by_ids() -> None:
    now = datetime(2026, 5, 4, tzinfo=UTC)
    ready = _issue("10001", "DEMO-1", "Ready", now)
    done = _issue("10002", "DEMO-2", "Done", now)

    tracker = MemoryTracker([ready, done], active_state_names=["ready"])

    assert tracker.fetch_issue_states_by_ids(["10002", "missing", "10001"]) == {
        "10002": "Done",
        "10001": "Ready",
    }


def _issue(
    issue_id: str,
    identifier: str,
    state: str,
    created_at: datetime,
    *,
    priority: int | None = None,
    blocked_by: tuple[str, ...] = (),
) -> Issue:
    return Issue(
        id=issue_id,
        identifier=identifier,
        title=f"Issue {identifier}",
        state=state,
        created_at=created_at,
        updated_at=created_at,
        priority=priority,
        blocked_by=blocked_by,
    )
