"""Strict prompt rendering for workflow templates."""

from __future__ import annotations

import re
from dataclasses import dataclass

from synphony.errors import TemplateRenderError
from synphony.models import Issue, RunAttempt

_VARIABLE_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*}}")


@dataclass(frozen=True, slots=True)
class _AttemptView:
    number: int
    issue_id: str
    issue_identifier: str

    @classmethod
    def from_attempt(cls, attempt: RunAttempt) -> _AttemptView:
        return cls(
            number=attempt.attempt,
            issue_id=attempt.issue_id,
            issue_identifier=attempt.issue_identifier,
        )


def render_prompt(template: str, *, issue: Issue, attempt: RunAttempt) -> str:
    """Render a workflow prompt with strict variable resolution."""
    context = {"issue": issue, "attempt": _AttemptView.from_attempt(attempt)}

    def replace(match: re.Match[str]) -> str:
        variable = match.group(1)
        value = _resolve_variable(variable, context)
        return str(value)

    return _VARIABLE_PATTERN.sub(replace, template)


def build_first_prompt(template: str, *, issue: Issue, attempt: RunAttempt) -> str:
    """Build the first provider prompt from the workflow template."""
    return render_prompt(template, issue=issue, attempt=attempt)


def build_continuation_prompt(*, issue: Issue, attempt: RunAttempt) -> str:
    """Build provider-agnostic continuation guidance for follow-up turns."""
    return (
        f"Continue work on {issue.identifier} from the existing session. "
        f"This is attempt {attempt.attempt}; do not restart completed work. "
        "Inspect the workspace, continue from the current state, and stop when the task is done."
    )


def _resolve_variable(variable: str, context: dict[str, object]) -> object:
    parts = variable.split(".")
    current: object = context.get(parts[0], _Missing)
    if current is _Missing:
        raise TemplateRenderError(f"unknown variable: {variable}")

    for part in parts[1:]:
        if part.startswith("_") or not hasattr(current, part):
            raise TemplateRenderError(f"unknown variable: {variable}")
        current = getattr(current, part)

    return current


class _MissingType:
    pass


_Missing = _MissingType()
