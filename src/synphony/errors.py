"""Shared error taxonomy for synphony."""

from __future__ import annotations

from typing import Any


class SynphonyError(Exception):
    """Base class for stable, structured synphony errors."""

    code = "synphony_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class WorkflowError(SynphonyError):
    code = "workflow_error"


class WorkflowNotFoundError(WorkflowError):
    code = "workflow_not_found"


class WorkflowParseError(WorkflowError):
    code = "workflow_parse_error"


class ConfigError(SynphonyError):
    code = "config_error"


class ConfigValidationError(ConfigError):
    code = "config_validation_error"


class TemplateRenderError(SynphonyError):
    code = "template_render_error"


class AcliNotFoundError(SynphonyError):
    code = "acli_not_found"

    def __init__(self) -> None:
        super().__init__("acli was not found on PATH")


class JiraQueryFailedError(SynphonyError):
    code = "jira_query_failed"


class TrackerParseError(SynphonyError):
    code = "tracker_parse_error"


class WorkspacePathError(SynphonyError):
    code = "workspace_path_error"


class WorkspaceHookError(SynphonyError):
    code = "workspace_hook_error"


class AgentError(SynphonyError):
    code = "agent_error"


class AgentNotFoundError(AgentError):
    code = "agent_not_found"


class AgentProtocolError(AgentError):
    code = "agent_protocol_error"


class AgentTimeoutError(AgentError):
    code = "agent_timeout"

    def __init__(self, *, provider: str, timeout_ms: int) -> None:
        super().__init__(
            f"{provider} agent timed out after {timeout_ms}ms",
            details={"provider": provider, "timeout_ms": timeout_ms},
        )
