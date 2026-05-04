# Release Readiness

This document tracks the Phase 7 definition-of-done pass for the first usable `synphony-py` milestone.

## Current Phase 7 Status

- Workflow examples are present for Codex and Claude under `docs/examples/`.
- Example workflows are covered by unit tests that load the YAML front matter and validate the selected provider config.
- CI runs tests, linting, formatting checks, and mypy without requiring Jira, Codex, or Claude credentials.
- Integration smoke tests are not part of the default suite and should be added behind an explicit marker or manual workflow when real adapters exist.

## First Usable Milestone Checklist

| Requirement | Status | Notes |
| --- | --- | --- |
| Loads and hot-reloads `WORKFLOW.md` | Partial | Loader and reload store exist; runtime orchestration is not wired. |
| Polls Jira via `acli` | Blocked | Jira tracker adapter is not implemented in this worktree. |
| Creates safe workspaces and runs hooks | Blocked | Workspace manager and hook runner are not implemented in this worktree. |
| Supports Codex and Claude through `AgentBackend` | Blocked | Provider selection config exists; backend protocol and real adapters are not implemented in this worktree. |
| Reconciles state transitions and cleans terminal workspaces | Blocked | Orchestrator and cleanup behavior are not implemented in this worktree. |
| Emits structured logs | Blocked | Structured logging is not implemented in this worktree. |
| Future providers remain out of scope | Done | Config validation accepts only `codex` and `claude`. |

## Verification

Run the default local verification before release or PR merge:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Optional integration verification should be documented once Jira, Codex, and Claude adapters land. Those checks should require explicit credentials/tools and must not run in the default CI path.
