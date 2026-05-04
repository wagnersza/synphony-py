from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synphony.errors import AcliNotFoundError, JiraQueryFailedError
from synphony.tracker.jira_acli import JiraAcliTracker, parse_issue, parse_issue_list


def test_parse_issue_list_maps_jira_json_into_issues() -> None:
    payload = json.loads((_fixture_dir() / "search_issues.json").read_text(encoding="utf-8"))

    issues = parse_issue_list(payload)

    assert len(issues) == 1
    assert issues[0].id == "10001"
    assert issues[0].identifier == "DEMO-1"
    assert issues[0].state == "Ready"
    assert issues[0].priority == 2
    assert issues[0].labels == ("backend", "phase-2")
    assert issues[0].blocked_by == ("DEMO-0",)
    assert issues[0].created_at == datetime(2026, 5, 4, 10, 0, tzinfo=UTC)


def test_parse_issue_accepts_flat_acli_json_shape() -> None:
    issue = parse_issue(
        {
            "id": "10001",
            "key": "DEMO-1",
            "summary": "Flat issue",
            "status": "In Progress",
            "created": "2026-05-04T10:00:00Z",
            "updated": "2026-05-04T11:00:00Z",
            "priority": 1,
            "labels": ["flat"],
            "blocked_by": ["DEMO-0"],
        }
    )

    assert issue.identifier == "DEMO-1"
    assert issue.state == "In Progress"
    assert issue.priority == 1
    assert issue.blocked_by == ("DEMO-0",)


def test_jira_tracker_invokes_acli_with_json_and_timeout() -> None:
    calls: list[tuple[list[str], float]] = []

    def runner(command: list[str], timeout_s: float) -> str:
        calls.append((command, timeout_s))
        return '{"issues": []}'

    tracker = JiraAcliTracker(
        jql="project = DEMO",
        active_state_names=["Ready"],
        runner=runner,
        timeout_s=12.5,
    )

    assert tracker.fetch_candidate_issues() == []
    assert calls == [
        (
            [
                "acli",
                "jira",
                "workitem",
                "search",
                "--jql",
                'project = DEMO AND status in ("Ready")',
                "--fields",
                "key,summary,status,description,priority,labels,issuelinks,created,updated",
                "--limit",
                "50",
                "--json",
            ],
            12.5,
        )
    ]


def test_jira_tracker_fetches_states_by_ids() -> None:
    responses = iter(
        [
            '{"id":"10001","key":"DEMO-1","fields":{"summary":"One","status":{"name":"Ready"}}}',
            '{"id":"10002","key":"DEMO-2","fields":{"summary":"Two","status":{"name":"Done"}}}',
        ]
    )

    def runner(command: list[str], timeout_s: float) -> str:
        return next(responses)

    tracker = JiraAcliTracker(
        jql="project = DEMO",
        active_state_names=["Ready"],
        runner=runner,
    )

    assert tracker.fetch_issue_states_by_ids(["10001", "10002"]) == {
        "10001": "Ready",
        "10002": "Done",
    }


def test_jira_tracker_maps_missing_acli_and_failed_queries() -> None:
    def missing_runner(command: list[str], timeout_s: float) -> str:
        raise FileNotFoundError

    tracker = JiraAcliTracker(
        jql="project = DEMO",
        active_state_names=["Ready"],
        runner=missing_runner,
    )

    with pytest.raises(AcliNotFoundError):
        tracker.fetch_candidate_issues()

    def failing_runner(command: list[str], timeout_s: float) -> str:
        raise JiraQueryFailedError("bad query")

    tracker = JiraAcliTracker(
        jql="project = DEMO",
        active_state_names=["Ready"],
        runner=failing_runner,
    )

    with pytest.raises(JiraQueryFailedError):
        tracker.fetch_candidate_issues()


def _fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures" / "acli"
