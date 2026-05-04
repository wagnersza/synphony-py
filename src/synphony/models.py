"""Core domain models shared across synphony components."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

AgentProvider = Literal["codex", "claude"]
IssueState = str


def normalize_state_name(state: str) -> str:
    """Normalize tracker state names for case-insensitive comparisons."""
    return " ".join(state.strip().casefold().split())


def workspace_key_from_identifier(identifier: str) -> str:
    """Convert an issue identifier into a conservative workspace directory name."""
    key = re.sub(r"[^a-z0-9]+", "-", identifier.casefold()).strip("-")
    return key or "issue"


def build_session_id(*, provider: str, thread_id: str | None, turn_id: str | None) -> str:
    """Build a normalized session id from provider-specific identifiers."""
    parts = [provider]
    parts.extend(part for part in (thread_id, turn_id) if part)
    return ":".join(parts)


@dataclass(frozen=True, slots=True)
class Issue:
    id: str
    identifier: str
    title: str
    state: IssueState
    created_at: datetime
    updated_at: datetime
    description: str | None = None
    priority: int | None = None
    labels: tuple[str, ...] = ()
    url: str | None = None
    blocked_by: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_state(self) -> str:
        return normalize_state_name(self.state)

    @property
    def workspace_key(self) -> str:
        return workspace_key_from_identifier(self.identifier)

    @property
    def is_blocked(self) -> bool:
        return bool(self.blocked_by)


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    path: str
    config: dict[str, Any]
    prompt_template: str
    loaded_at: datetime


@dataclass(frozen=True, slots=True)
class Workspace:
    path: str
    key: str
    created_now: bool


@dataclass(frozen=True, slots=True)
class RunAttempt:
    issue_id: str
    issue_identifier: str
    attempt: int


@dataclass(frozen=True, slots=True)
class AgentUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class AgentEvent:
    provider: str
    session_id: str
    kind: str
    occurred_at: datetime
    turn_id: str | None = None
    message: str | None = None
    usage: AgentUsage | None = None
    rate_limits: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LiveSession:
    issue: Issue
    workspace: Workspace
    attempt: RunAttempt
    provider: str
    session_id: str
    started_at: datetime
    last_event_at: datetime


@dataclass(frozen=True, slots=True)
class RetryEntry:
    issue: Issue
    attempt: RunAttempt
    next_retry_at: datetime
    reason: str
    backoff_ms: int


@dataclass(slots=True)
class RuntimeState:
    claimed_issue_ids: set[str] = field(default_factory=set)
    running: dict[str, LiveSession] = field(default_factory=dict)
    retries: list[RetryEntry] = field(default_factory=list)
