# Implementation Plan: Jira to Claude Run-Once

## Overview

Build the smallest production-shaped path that can fetch one eligible Jira issue
with `acli`, prepare a workspace, and run one Claude Code CLI agent session
against that issue. This plan intentionally targets a `--once` smoke-test flow
before the full long-running daemon, because the current `Orchestrator` and
`AgentRunner` boundaries are not yet wired for asynchronous live sessions.

## Architecture Decisions

- Start with `synphony --once <WORKFLOW.md>` instead of daemon mode. A single-run
command is easier to verify with real Jira and Claude credentials.
- Keep Jira access behind the existing `JiraAcliTracker`; do not add Jira logic
to the agent backend or CLI.
- Implement Claude as a normal `AgentBackend` so the same `AgentRunner` tests and
future orchestrator integration can reuse it.
- Treat the Claude Code CLI contract as an external boundary. Capture success,
failure, timeout, and continuation behavior in tests before relying on it.

## Dependency Graph

```text
Claude CLI contract spike
    |
    v
ClaudeBackend
    |
    v
Config getters --------> Backend registry factory
    |                         |
    +------------+------------+
                 v
          CLI --once flow
                 |
                 v
       Real Jira + Claude smoke test
```

## Task 1: Implement Claude CLI Backend

**Description:** Add a real Claude backend that satisfies `AgentBackend`, runs the
configured Claude command from the prepared workspace, feeds the rendered prompt,
and normalizes process output into `AgentTurnResult` events.

**Acceptance criteria:**

- First turns run from `AgentTurnInput.workspace.path` and return a stable
`session_id`.
- Success, nonzero exit, missing executable, timeout, and malformed output map to
existing Synphony error/event semantics.
- Continuation turns either resume a prior Claude session if the CLI supports it
or fail clearly with a documented unsupported-continuation error.

**Verification:**

- Add `tests/test_claude_backend.py` with mocked subprocess tests for success,
failure, missing binary, timeout, and continuation.
- Add sanitized fixture output under `tests/fixtures/claude/` if the CLI exposes
structured output.
- Run `uv run pytest tests/test_claude_backend.py tests/test_agent_runner.py`.

**Dependencies:** Claude Code CLI contract spike.

**Files likely touched:**

- `src/synphony/agents/claude.py`
- `src/synphony/errors.py`
- `tests/test_claude_backend.py`
- `tests/fixtures/claude/`

**Estimated scope:** Medium.

## Task 2: Add Runtime Config Getters

**Description:** Extend `SynphonyConfig` with typed accessors needed by run mode
while preserving current workflow validation behavior.

**Acceptance criteria:**

- Config exposes tracker active states, terminal states, workspace hook settings,
agent max turns, and optional turn timeout.
- Defaults match the example workflows and existing test expectations.
- Invalid types fail with `ConfigValidationError` and clear field paths.

**Verification:**

- Extend `tests/test_config.py` for defaults, configured values, and invalid
values.
- Run `uv run pytest tests/test_config.py tests/test_cli.py`.

**Dependencies:** None.

**Files likely touched:**

- `src/synphony/config.py`
- `tests/test_config.py`
- `docs/examples/WORKFLOW.claude.md` if defaults or names change

**Estimated scope:** Small.

## Task 3: Wire Real Claude Backend Selection

**Description:** Replace the reserved Claude placeholder with construction logic
that returns `ClaudeBackend` for workflows selecting `agent.provider: claude`.

**Acceptance criteria:**

- Provider selection uses the configured command instead of hard-coded `claude`.
- `codex` can remain reserved until its backend lands.
- Unsupported or unimplemented providers still fail clearly.

**Verification:**

- Update `tests/test_agent_registry.py` or add focused factory tests.
- Run `uv run pytest tests/test_agent_registry.py tests/test_cli.py`.

**Dependencies:** Tasks 1 and 2.

**Files likely touched:**

- `src/synphony/agents/registry.py`
- `src/synphony/agents/__init__.py`
- `tests/test_agent_registry.py`

**Estimated scope:** Small.

## Task 4: Add CLI `--once` Flow

**Description:** Add a single-run CLI mode that loads a workflow, fetches one Jira
candidate, prepares a workspace, runs Claude through `AgentRunner`, and prints a
brief result summary.

**Acceptance criteria:**

- `uv run synphony --once docs/examples/WORKFLOW.claude.md` validates config and
attempts exactly one issue.
- If no Jira candidates exist, the command exits successfully with a clear
"no candidate issues" message.
- Agent success, agent failure, Jira failure, and workspace hook failure return
distinct nonzero exit paths where applicable.
- `--check` behavior remains unchanged.

**Verification:**

- Extend `tests/test_cli.py` with fake tracker/backend injection or a small CLI
composition helper that can be tested without real Jira or Claude.
- Run `uv run pytest tests/test_cli.py tests/test_jira_acli.py tests/test_agent_runner.py`.
- Manual smoke test with authenticated tools:
  ```bash
  acli jira workitem search --jql 'project = DEMO AND status in ("Ready")' --limit 1 --json
  uv run synphony --once docs/examples/WORKFLOW.claude.md
  ```

**Dependencies:** Tasks 1, 2, and 3.

**Files likely touched:**

- `src/synphony/cli.py`
- `src/synphony/config.py`
- `tests/test_cli.py`
- `README.md`

**Estimated scope:** Medium.

## Checkpoint: First End-to-End Smoke Path

- `uv run pytest tests/test_claude_backend.py tests/test_config.py tests/test_agent_registry.py tests/test_cli.py` passes.
- `uv run synphony --check docs/examples/WORKFLOW.claude.md` still passes.
- `uv run synphony --once docs/examples/WORKFLOW.claude.md` can fetch one Jira issue and invoke Claude in the issue workspace.
- Any real integration test is gated behind explicit local credentials and is skipped by default in CI.

## Risks and Mitigations

- Claude CLI may not expose stable structured output. Mitigate by starting with
process-level success/failure events and documenting the unsupported details.
- Claude continuation/resume may require a provider-specific session file or
command flag. Mitigate by making continuation explicit: support it only after
the spike confirms the contract.
- Real Jira smoke tests can mutate or pick unsafe work. Mitigate by requiring a
dedicated test project/JQL and documenting that `--once` should target a safe
issue.
- Workspace hooks can make smoke tests slow or flaky. Mitigate by allowing a
minimal workflow without heavyweight hooks for integration testing.

## Open Questions

- Which Claude Code CLI command form should be considered canonical for
non-interactive execution?
- Should `--once` transition or comment on Jira issues after completion, or only
run the agent and leave Jira mutation manual for now?
- Should the first `--once` implementation use the `Orchestrator` at all, or keep
direct CLI composition until async session management exists?

