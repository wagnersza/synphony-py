# Production Plan: Symphony Spec Compliance with Jira and Claude Code

## Purpose

This plan validates the current `synphony-py` development state against
`../symphony/SPEC.md` and defines the ordered work needed to reach production
readiness for the chosen product profile:

- Issue tracker: Jira through the Atlassian CLI, `acli`.
- Agent provider: Claude Code CLI.
- Runtime shape: the Symphony long-running scheduler/runner service, not only a
one-shot smoke-test command.

The upstream spec is Linear- and Codex-centered. This project intentionally
adapts those extension points to Jira and Claude. The adaptation must be
documented as an implementation contract so the code remains spec-coherent
instead of silently diverging.

## Current Validation Baseline

Verified on 2026-05-04:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Result:

- `62 passed`
- Ruff lint passed
- Ruff format check passed
- Mypy strict passed

The current implementation is internally consistent and well-tested for the
bootstrap slice. The remaining work is primarily product/spec completeness.

## Current Implementation Snapshot

Implemented:

- Python package, strict test/lint/type tooling, and CLI entry point.
- Workflow loader with YAML front matter and prompt body parsing.
- Basic typed config validation for `tracker.kind: jira` and
`agent.provider: codex | claude`.
- Strict prompt interpolation for simple `{{ issue.* }}` and `{{ attempt.* }}`
variables.
- Reloadable `WorkflowStore` that keeps the last good workflow after invalid
reloads.
- Domain models for issues, workspaces, attempts, events, live sessions,
retries, and runtime state.
- In-memory tracker for deterministic tests.
- Jira `acli` tracker adapter with JSON parsing and basic error mapping.
- Workspace manager with deterministic paths, root containment checks, and
lifecycle hooks.
- Provider-neutral `AgentBackend` protocol, fake test backend, registry
placeholders for `codex` and `claude`.
- Provider-neutral `AgentRunner` loop using fake backends.
- Orchestrator dispatch/reconciliation unit behavior for candidates,
concurrency caps, blocking, terminal cleanup, and stall retries.
- Structured JSON logging.
- `synphony --check` workflow validation.

Not production-ready yet:

- No real Claude Code backend.
- No real Codex backend. If strict upstream conformance is required in addition
to the Jira/Claude product profile, Codex still must be implemented.
- No long-running CLI service loop.
- No worker spawning model that lets the orchestrator own live sessions while
agent runs execute concurrently.
- No startup terminal workspace cleanup wired into startup.
- No retry dispatch loop for normal worker exits and failure backoff.
- No dynamic workflow reload wired into the running service.
- No real Jira + Claude integration profile.

## Compliance Profile Decisions

Before implementation, record these decisions in `docs/ARCHITECTURE.md` or a
dedicated compliance note.

- `tracker.kind: jira` is the production tracker extension. It replaces the
spec's Linear-specific fields while preserving the tracker adapter operations:
candidate fetch, fetch by states, and state refresh by IDs.
- `agent.provider: claude` is a production agent-provider extension. Claude
provider behavior must map to the shared `AgentBackend` contract and document
any Claude CLI limitations around sessions, continuations, usage metrics,
approvals, and user-input-required signals.
- `synphony --once` may exist only as a smoke-test helper. The production
service must implement the spec's long-running poll/reconcile/dispatch loop.
- Ticket writes remain outside the orchestrator. Jira transitions, comments,
and PR links should be performed by the agent through workflow instructions or
explicit tools, not by hidden scheduler business logic.
- Unknown top-level workflow keys should be ignored for forward compatibility
unless the project explicitly chooses stricter validation and documents it.

## Detailed Task Breakdown

Use these tasks as the implementation backlog. Each task is intended to be small
enough for one focused implementation session and should leave the repository in
a passing state.

### Foundation and Contracts

#### Task 1: Document the Jira and Claude Compliance Profile

**Description:** Record the intentional departures from the Linear/Codex
upstream spec and define the production contract for `tracker.kind: jira` and
`agent.provider: claude`.

**Acceptance criteria:**

- `docs/ARCHITECTURE.md` names Jira and Claude as explicit spec extensions.
- The doc states that `--once`, if implemented, is a smoke-test helper rather
than the production service path.
- The doc states the tracker-write boundary and Claude approval/user-input
policy decisions that are already known.

**Verification:**

- Run `uv run pytest tests/test_examples.py`.
- Manual review confirms the compliance profile answers the open product
questions that block implementation.

**Dependencies:** None.

**Files likely touched:**

- `docs/ARCHITECTURE.md`
- `README.md`

**Estimated scope:** Small.

#### Task 2: Make Workflow Front Matter Spec-Compatible

**Description:** Update workflow loading so front matter is optional and prompt
body trimming matches the spec.

**Acceptance criteria:**

- A file without YAML front matter loads with `{}` config and the full file
as prompt text.
- Existing front-matter workflows still parse.
- Invalid YAML and non-map front matter still fail with typed workflow
errors.

**Verification:**

- Add/adjust tests in `tests/test_workflow.py`.
- Run `uv run pytest tests/test_workflow.py`.

**Dependencies:** Task 1.

**Files likely touched:**

- `src/synphony/workflow.py`
- `tests/test_workflow.py`

**Estimated scope:** Small.

#### Task 3: Resolve Workflow-Relative Paths

**Description:** Teach config resolution where the selected workflow file lives
so relative `workspace.root` values resolve relative to that file rather than the
process cwd.

**Acceptance criteria:**

- `workspace.root: .synphony/workspaces` resolves under the workflow file's
directory.
- `~` and `$VAR` still resolve for path fields.
- Non-path command strings are not environment-expanded accidentally.

**Verification:**

- Extend `tests/test_config.py` for workflow-relative paths.
- Run `uv run pytest tests/test_config.py`.

**Dependencies:** Task 2.

**Files likely touched:**

- `src/synphony/config.py`
- `src/synphony/cli.py`
- `tests/test_config.py`

**Estimated scope:** Small.

#### Task 4: Add Runtime Config Getters

**Description:** Add typed getters for every runtime field needed by the
orchestrator, workspace manager, Jira tracker, and Claude backend.

**Acceptance criteria:**

- Config exposes active states, terminal states, polling interval,
concurrency limits, per-state caps, max turns, retry backoff cap, hook
commands, hook timeout, provider command, and provider timeouts.
- Invalid types and invalid numeric ranges raise `ConfigValidationError`.
- Defaults are documented and tested.

**Verification:**

- Extend `tests/test_config.py` for each getter.
- Run `uv run pytest tests/test_config.py tests/test_cli.py`.

**Dependencies:** Task 3.

**Files likely touched:**

- `src/synphony/config.py`
- `tests/test_config.py`
- `docs/examples/WORKFLOW.claude.md`

**Estimated scope:** Medium.

#### Task 5: Move Hook Config to Top-Level `hooks`

**Description:** Align examples and config access with the spec's top-level
`hooks` block instead of `workspace.hooks`.

**Acceptance criteria:**

- Examples use top-level `hooks.before_run`.
- Config reads `hooks.after_create`, `hooks.before_run`, `hooks.after_run`,
`hooks.before_remove`, and `hooks.timeout_ms`.
- Old `workspace.hooks` usage is either rejected clearly or documented as
unsupported.

**Verification:**

- Extend `tests/test_config.py` and `tests/test_examples.py`.
- Run `uv run pytest tests/test_config.py tests/test_examples.py`.

**Dependencies:** Task 4.

**Files likely touched:**

- `src/synphony/config.py`
- `docs/examples/WORKFLOW.claude.md`
- `docs/examples/WORKFLOW.codex.md`
- `tests/test_config.py`
- `tests/test_examples.py`

**Estimated scope:** Small.

### Data Model and Workspace Safety

#### Task 6: Normalize Jira Issue Fields

**Description:** Update issue normalization so Jira labels, blockers, and
optional metadata are represented consistently with the spec-compatible internal
model.

**Acceptance criteria:**

- Labels normalize to lowercase.
- Jira blocker data preserves identifier and, when available, state/id.
- The chosen blocker representation is usable by dispatch eligibility and
prompt rendering.

**Verification:**

- Extend `tests/test_models.py` and `tests/test_jira_acli.py`.
- Run `uv run pytest tests/test_models.py tests/test_jira_acli.py`.

**Dependencies:** Task 1.

**Files likely touched:**

- `src/synphony/models.py`
- `src/synphony/tracker/jira_acli.py`
- `tests/test_models.py`
- `tests/test_jira_acli.py`

**Estimated scope:** Medium.

#### Task 7: Enrich Live Session and Retry State

**Description:** Add provider-neutral runtime fields needed for retries,
observability, usage accounting, and stall detection.

**Acceptance criteria:**

- `LiveSession` tracks turn count, last event kind/message/time, provider,
and usage fields when available.
- `RetryEntry` carries attempt, due time, issue identifier, reason/error, and
backoff.
- Existing orchestrator tests are updated without weakening behavior.

**Verification:**

- Extend `tests/test_models.py` and `tests/test_orchestrator.py`.
- Run `uv run pytest tests/test_models.py tests/test_orchestrator.py`.

**Dependencies:** Task 6.

**Files likely touched:**

- `src/synphony/models.py`
- `src/synphony/orchestrator.py`
- `tests/test_models.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Medium.

#### Task 8: Fix Workspace Collision and Hook Failure Semantics

**Description:** Make workspace creation and hooks match the spec's failure
semantics, including best-effort cleanup hooks.

**Acceptance criteria:**

- Existing non-directory workspace paths fail safely.
- `after_create` and `before_run` failures are fatal.
- `after_run` and `before_remove` failures are logged and ignored.
- Hook timeout comes from `hooks.timeout_ms`.

**Verification:**

- Extend `tests/test_workspace.py` for non-directory collision and ignored
hook failures.
- Run `uv run pytest tests/test_workspace.py tests/test_logging.py`.

**Dependencies:** Task 5.

**Files likely touched:**

- `src/synphony/workspace.py`
- `src/synphony/logging.py`
- `tests/test_workspace.py`
- `tests/test_logging.py`

**Estimated scope:** Medium.

#### Task 9: Add Agent Launch Workspace Preflight

**Description:** Add a shared preflight check that validates the agent subprocess
will launch from the exact per-issue workspace under the configured root.

**Acceptance criteria:**

- Agent launch checks `cwd == workspace.path`.
- Agent launch checks the workspace path remains under workspace root.
- Failures use a typed workspace or agent error.

**Verification:**

- Extend `tests/test_agent_runner.py` or backend tests once the preflight
helper exists.
- Run `uv run pytest tests/test_agent_runner.py tests/test_workspace.py`.

**Dependencies:** Task 8.

**Files likely touched:**

- `src/synphony/workspace.py`
- `src/synphony/agent_runner.py`
- `src/synphony/agents/claude.py`
- `tests/test_agent_runner.py`

**Estimated scope:** Small.

### Jira Tracker

#### Task 10: Add Empty-State and Pagination Behavior to Jira Tracker

**Description:** Harden candidate and by-state Jira reads for production-scale
queries.

**Acceptance criteria:**

- `fetch_issues_by_states([])` returns `[]` without invoking `acli`.
- Candidate fetch handles configured pagination or a documented bounded
limit.
- Pagination preserves Jira result order.

**Verification:**

- Extend `tests/test_jira_acli.py` for empty states and multiple pages.
- Run `uv run pytest tests/test_jira_acli.py`.

**Dependencies:** Task 4.

**Files likely touched:**

- `src/synphony/tracker/jira_acli.py`
- `tests/test_jira_acli.py`
- `tests/fixtures/acli/`

**Estimated scope:** Medium.

#### Task 11: Improve Jira State Refresh for Reconciliation

**Description:** Make running-issue refresh efficient and rich enough for
orchestrator reconciliation.

**Acceptance criteria:**

- Refresh can update running issue snapshots, not only state strings, or the
tracker protocol documents why state-only refresh is sufficient.
- If `acli` supports bulk fetch, use it; otherwise document per-issue calls
and add concurrency/timeout safeguards.
- Missing issue IDs are handled without crashing reconciliation.

**Verification:**

- Extend `tests/test_jira_acli.py` and `tests/test_orchestrator.py`.
- Run `uv run pytest tests/test_jira_acli.py tests/test_orchestrator.py`.

**Dependencies:** Task 10.

**Files likely touched:**

- `src/synphony/tracker/base.py`
- `src/synphony/tracker/jira_acli.py`
- `src/synphony/orchestrator.py`
- `tests/test_jira_acli.py`

**Estimated scope:** Medium.

#### Task 12: Complete Jira Error Taxonomy

**Description:** Map real `acli` failure modes to stable Synphony errors for
operators and retry decisions.

**Acceptance criteria:**

- Missing binary, timeout, nonzero exit, invalid JSON, missing required
fields, and pagination integrity failures each have stable error codes.
- Error details include safe command metadata without secrets or large raw
payloads.
- CLI/operator logs surface the error code.

**Verification:**

- Extend `tests/test_jira_acli.py` and `tests/test_logging.py`.
- Run `uv run pytest tests/test_jira_acli.py tests/test_logging.py`.

**Dependencies:** Task 10.

**Files likely touched:**

- `src/synphony/errors.py`
- `src/synphony/tracker/jira_acli.py`
- `tests/test_jira_acli.py`

**Estimated scope:** Small.

#### Task 13: Capture Real Jira Command Fixtures

**Description:** Verify the target `acli` commands against the authenticated Jira
environment and save sanitized fixtures for tests.

**Acceptance criteria:**

- `docs/ARCHITECTURE.md` lists the verified `acli` version and commands.
- Sanitized search, view, pagination, blocked, and malformed/edge fixtures
exist.
- Fixture tests cover fields used by production code.

**Verification:**

- Run documented `acli` commands manually.
- Run `uv run pytest tests/test_jira_acli.py`.

**Dependencies:** Tasks 10, 11, and 12.

**Files likely touched:**

- `docs/ARCHITECTURE.md`
- `tests/fixtures/acli/`
- `tests/test_jira_acli.py`

**Estimated scope:** Small.

### Claude Backend

#### Task 14: Spike the Claude Code CLI Contract

**Description:** Discover and document the machine-safe Claude Code CLI flow
before implementing the backend.

**Acceptance criteria:**

- Documentation covers command form, stdin/stdout/stderr behavior, exit
codes, structured output, session/resume support, timeout behavior, approval
behavior, and user-input behavior.
- The plan explicitly says whether continuation turns are supported.
- Any unsupported spec concepts are listed.

**Verification:**

- Run harmless local Claude CLI smoke commands.
- Save sanitized sample output if structured output exists.

**Dependencies:** Task 1.

**Files likely touched:**

- `docs/ARCHITECTURE.md`
- `tests/fixtures/claude/`
- `README.md`

**Estimated scope:** Medium.

#### Task 15: Add `ClaudeBackend` Process Runner

**Description:** Implement the first-turn Claude backend path using the
documented CLI contract.

**Acceptance criteria:**

- `ClaudeBackend` implements `AgentBackend`.
- First turns launch from the per-issue workspace.
- Success returns an `AgentTurnResult` with normalized events.
- Missing executable, nonzero exit, and timeout produce typed errors/events.

**Verification:**

- Add `tests/test_claude_backend.py` for first-turn success and failure
paths.
- Run `uv run pytest tests/test_claude_backend.py`.

**Dependencies:** Tasks 9 and 14.

**Files likely touched:**

- `src/synphony/agents/claude.py`
- `src/synphony/errors.py`
- `tests/test_claude_backend.py`

**Estimated scope:** Medium.

#### Task 16: Implement Claude Continuation Policy

**Description:** Add continuation behavior based on the spike result: true
session resume when supported, or a documented clear failure when unsupported.

**Acceptance criteria:**

- `continue_session()` either resumes the previous Claude session or fails
with a stable unsupported-continuation error.
- `AgentRunner` can distinguish unsupported continuation from generic agent
failure.
- Documentation matches the implemented policy.

**Verification:**

- Extend `tests/test_claude_backend.py` and `tests/test_agent_runner.py`.
- Run `uv run pytest tests/test_claude_backend.py tests/test_agent_runner.py`.

**Dependencies:** Task 15.

**Files likely touched:**

- `src/synphony/agents/claude.py`
- `src/synphony/agent_runner.py`
- `docs/ARCHITECTURE.md`
- `tests/test_claude_backend.py`

**Estimated scope:** Medium.

#### Task 17: Normalize Claude Events and Usage

**Description:** Parse Claude output into provider-neutral events and usage data
where the CLI exposes it.

**Acceptance criteria:**

- Session start, turn start, output/notification, completion, failure,
timeout, user-input-required, and malformed output are represented as
`AgentEvent` values where applicable.
- Usage/rate-limit fields are populated when available and left null when
unavailable.
- Large raw output is not logged by default.

**Verification:**

- Extend `tests/test_claude_backend.py` using sanitized fixtures.
- Run `uv run pytest tests/test_claude_backend.py tests/test_logging.py`.

**Dependencies:** Task 15.

**Files likely touched:**

- `src/synphony/agents/claude.py`
- `src/synphony/models.py`
- `tests/test_claude_backend.py`
- `tests/fixtures/claude/`

**Estimated scope:** Medium.

#### Task 18: Wire Backend Factory for Claude

**Description:** Replace the placeholder Claude registry entry with real
construction from workflow config.

**Acceptance criteria:**

- `agent.provider: claude` constructs `ClaudeBackend` with the configured
command and timeouts.
- `agent.provider: codex` still fails clearly until Codex is implemented or
explicitly out of scope.
- Unsupported providers still raise `AgentNotFoundError`.

**Verification:**

- Extend `tests/test_agent_registry.py`.
- Run `uv run pytest tests/test_agent_registry.py tests/test_config.py`.

**Dependencies:** Tasks 4 and 15.

**Files likely touched:**

- `src/synphony/agents/registry.py`
- `src/synphony/agents/__init__.py`
- `tests/test_agent_registry.py`

**Estimated scope:** Small.

### Agent Runner

#### Task 19: Make `after_run` Best-Effort in Agent Runner

**Description:** Ensure `after_run` always runs after an attempt and never masks
the primary attempt result.

**Acceptance criteria:**

- `after_run` runs after success, failure, timeout, prompt failure, and
cancellation paths when a workspace exists.
- `after_run` failures are logged and ignored.
- Primary failure reason is preserved.

**Verification:**

- Extend `tests/test_agent_runner.py`.
- Run `uv run pytest tests/test_agent_runner.py tests/test_workspace.py`.

**Dependencies:** Task 8.

**Files likely touched:**

- `src/synphony/agent_runner.py`
- `src/synphony/workspace.py`
- `tests/test_agent_runner.py`

**Estimated scope:** Medium.

#### Task 20: Classify Agent Runner Stop Reasons

**Description:** Expand runner outcomes so orchestrator retry logic can
distinguish normal exits from failure classes.

**Acceptance criteria:**

- Stop reasons distinguish inactive, max turns, agent failure, timeout,
prompt failure, hook failure, and state-refresh failure.
- Backend exceptions are converted to runner results or typed failures
consistently.
- Existing tests remain behavior-focused.

**Verification:**

- Extend `tests/test_agent_runner.py` and `tests/test_agent_fakes.py`.
- Run `uv run pytest tests/test_agent_runner.py tests/test_agent_fakes.py`.

**Dependencies:** Tasks 16 and 19.

**Files likely touched:**

- `src/synphony/agent_runner.py`
- `src/synphony/errors.py`
- `tests/test_agent_runner.py`
- `tests/fakes.py`

**Estimated scope:** Medium.

#### Task 21: Forward Runner Events for Orchestrator State Updates

**Description:** Make runner/provider events update live session timestamps,
turn count, messages, usage, and rate limits through a callback contract.

**Acceptance criteria:**

- Every provider event reaches the orchestrator callback.
- Last-event timestamp supports stall detection.
- Usage and rate-limit data can be aggregated when available.

**Verification:**

- Extend `tests/test_agent_runner.py` and `tests/test_orchestrator.py`.
- Run `uv run pytest tests/test_agent_runner.py tests/test_orchestrator.py`.

**Dependencies:** Tasks 7 and 17.

**Files likely touched:**

- `src/synphony/agent_runner.py`
- `src/synphony/orchestrator.py`
- `tests/test_agent_runner.py`

**Estimated scope:** Medium.

### Orchestrator and Service Loop

#### Task 22: Add Startup Terminal Workspace Cleanup

**Description:** Wire the tracker's terminal-state query to workspace cleanup at
service startup.

**Acceptance criteria:**

- Startup fetches terminal issues using configured terminal states.
- Matching workspaces are removed best-effort.
- Terminal fetch failure logs a warning and startup continues.

**Verification:**

- Extend `tests/test_orchestrator.py` or add service startup tests.
- Run `uv run pytest tests/test_orchestrator.py tests/test_workspace.py`.

**Dependencies:** Tasks 4 and 8.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `src/synphony/workspace.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Small.

#### Task 23: Implement Poll Tick Sequencing

**Description:** Add a deterministic tick function that reconciles, validates,
fetches candidates, dispatches, and reports observability state in spec order.

**Acceptance criteria:**

- Reconciliation runs before dispatch.
- Dispatch validation runs before candidate fetch.
- Candidate fetch errors skip dispatch and keep the service alive.
- Tick behavior is deterministic in tests.

**Verification:**

- Extend `tests/test_orchestrator.py`.
- Run `uv run pytest tests/test_orchestrator.py`.

**Dependencies:** Tasks 11, 20, and 22.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Medium.

#### Task 24: Correct Dispatch Eligibility and Blocker Policy

**Description:** Align dispatch eligibility with the selected Jira blocker
policy and spec sorting/capacity rules.

**Acceptance criteria:**

- Eligibility checks active state, terminal state, running, claimed,
retrying, global capacity, per-state capacity, and blockers.
- Blocker behavior is documented for Jira and tested.
- Candidate sorting remains priority, created time, identifier.

**Verification:**

- Extend `tests/test_orchestrator.py`.
- Run `uv run pytest tests/test_orchestrator.py`.

**Dependencies:** Tasks 6 and 23.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `tests/test_orchestrator.py`
- `docs/ARCHITECTURE.md`

**Estimated scope:** Medium.

#### Task 25: Implement Worker Launch and Live Session Tracking

**Description:** Add the worker execution model that lets the orchestrator own
live sessions while agent runs execute concurrently.

**Acceptance criteria:**

- Dispatch claims an issue before worker launch and records running state.
- Worker startup failures release or retry the claim safely.
- Live session entries update from runner events.
- Session stopper can terminate active provider sessions during
reconciliation/shutdown.

**Verification:**

- Add deterministic fake worker tests.
- Run `uv run pytest tests/test_orchestrator.py tests/test_agent_runner.py`.

**Dependencies:** Tasks 21, 23, and 24.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `src/synphony/agent_runner.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Large. Split if needed.

#### Task 26: Implement Retry Timers and Backoff Semantics

**Description:** Complete retry behavior for normal continuation, failures,
slot exhaustion, and retry timer firing.

**Acceptance criteria:**

- Normal worker exit schedules a short continuation retry.
- Abnormal worker exit schedules exponential backoff capped by config.
- Retry timers re-fetch active candidates and dispatch only if still
eligible.
- Slot exhaustion requeues with an explicit reason.

**Verification:**

- Extend `tests/test_orchestrator.py` for retry lifecycle cases.
- Run `uv run pytest tests/test_orchestrator.py`.

**Dependencies:** Task 25.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `src/synphony/models.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Medium.

#### Task 27: Implement Stall Detection and Reconciliation Stops

**Description:** Use provider-neutral last-event timestamps and tracker state
refreshes to stop or retry running sessions.

**Acceptance criteria:**

- Stall detection queues retries using configured timeout behavior.
- Terminal state stops the session and cleans the workspace.
- Non-active state stops the session without workspace cleanup.
- State-refresh failure keeps workers running until next tick.

**Verification:**

- Extend `tests/test_orchestrator.py`.
- Run `uv run pytest tests/test_orchestrator.py tests/test_workspace.py`.

**Dependencies:** Tasks 11 and 25.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `tests/test_orchestrator.py`

**Estimated scope:** Medium.

#### Task 28: Wire Dynamic Workflow Reload into Runtime

**Description:** Re-apply workflow/config changes during service operation while
keeping the last known good config on invalid reloads.

**Acceptance criteria:**

- Ticks or a watcher call `WorkflowStore.reload_if_changed()`.
- Valid reloads affect future dispatch, hooks, timeouts, states, and prompts.
- Invalid reloads log an operator-visible error and keep the service alive.

**Verification:**

- Extend `tests/test_workflow_store.py` and service/orchestrator tests.
- Run `uv run pytest tests/test_workflow_store.py tests/test_orchestrator.py`.

**Dependencies:** Tasks 4 and 23.

**Files likely touched:**

- `src/synphony/workflow_store.py`
- `src/synphony/orchestrator.py`
- `tests/test_workflow_store.py`

**Estimated scope:** Medium.

### CLI, Observability, and Integration

#### Task 29: Start the Production CLI Host

**Description:** Replace disabled run mode with a host process that builds the
runtime objects and starts the long-running service.

**Acceptance criteria:**

- `synphony <WORKFLOW.md>` starts the service.
- Missing workflow and startup validation failures return nonzero exits.
- `--check` remains validation-only.
- `--logs-root` configures structured file logs.

**Verification:**

- Extend `tests/test_cli.py` with fakes for startup composition.
- Run `uv run pytest tests/test_cli.py`.

**Dependencies:** Tasks 18, 23, and 28.

**Files likely touched:**

- `src/synphony/cli.py`
- `tests/test_cli.py`

**Estimated scope:** Medium.

#### Task 30: Add Graceful Shutdown

**Description:** Handle SIGINT/SIGTERM by stopping dispatch, terminating active
sessions, running best-effort hooks where appropriate, and flushing logs.

**Acceptance criteria:**

- Shutdown stops new dispatch.
- Active sessions are stopped through the backend stopper.
- Shutdown exits cleanly on SIGINT/SIGTERM.
- Abnormal host errors return nonzero exits.

**Verification:**

- Extend `tests/test_cli.py` or add host lifecycle tests with fake signals.
- Run `uv run pytest tests/test_cli.py tests/test_orchestrator.py`.

**Dependencies:** Task 29.

**Files likely touched:**

- `src/synphony/cli.py`
- `src/synphony/orchestrator.py`
- `tests/test_cli.py`

**Estimated scope:** Medium.

#### Task 31: Add Optional `--once` Smoke Path

**Description:** Add a non-production helper that runs exactly one eligible Jira
issue through Claude for local validation.

**Acceptance criteria:**

- `synphony --once <WORKFLOW.md>` attempts at most one eligible issue.
- No-candidate behavior exits successfully with a clear message.
- The command is documented as a smoke-test helper, not daemon behavior.

**Verification:**

- Extend `tests/test_cli.py`.
- Run `uv run pytest tests/test_cli.py`.

**Dependencies:** Tasks 18, 20, and 29.

**Files likely touched:**

- `src/synphony/cli.py`
- `README.md`
- `tests/test_cli.py`

**Estimated scope:** Small.

#### Task 32: Complete Structured Runtime Logging

**Description:** Ensure logs cover the required operator-visible lifecycle and
context fields.

**Acceptance criteria:**

- Logs include issue/session context for dispatch, worker, retry,
reconciliation, tracker, agent, and shutdown events.
- Log sink setup failures do not crash if another sink is available.
- Claude safety posture is documented.

**Verification:**

- Extend `tests/test_logging.py` and orchestrator tests.
- Run `uv run pytest tests/test_logging.py tests/test_orchestrator.py`.

**Dependencies:** Tasks 25, 27, and 29.

**Files likely touched:**

- `src/synphony/logging.py`
- `src/synphony/orchestrator.py`
- `README.md`
- `tests/test_logging.py`

**Estimated scope:** Medium.

#### Task 33: Add Gated Jira and Claude Integration Tests

**Description:** Add real integration tests that are skipped by default and prove
the production profile against safe external systems.

**Acceptance criteria:**

- Integration tests require explicit `SYNPHONY_INTEGRATION=1`.
- Tests skip clearly when `acli`, Jira auth, Claude CLI, or safe JQL is not
configured.
- Tests cover candidate fetch, no-candidate behavior, workspace creation,
and a harmless Claude run.

**Verification:**

- Run `uv run pytest tests/test_integration_jira_claude.py` and confirm
skipped behavior by default.
- Run `SYNPHONY_INTEGRATION=1 uv run pytest tests/test_integration_jira_claude.py`
in an authenticated test environment.

**Dependencies:** Tasks 13, 18, and 31.

**Files likely touched:**

- `tests/test_integration_jira_claude.py`
- `README.md`
- `docs/examples/WORKFLOW.claude.md`

**Estimated scope:** Medium.

#### Task 34: Add CI and Release Gate Documentation

**Description:** Define the repeatable quality gates for normal development and
the optional real integration profile for production readiness.

**Acceptance criteria:**

- CI runs pytest, Ruff lint, Ruff format check, and mypy.
- Integration profile is documented as manual or opt-in.
- README includes setup, auth, production run command, smoke-test command,
and known limitations.

**Verification:**

- Run the full local quality gate.
- Confirm CI config syntax in the selected provider.

**Dependencies:** Tasks 29 and 33.

**Files likely touched:**

- `.github/workflows/ci.yml`
- `README.md`

**Estimated scope:** Small.

## Phase 1: Workflow and Config Compliance

**Description:** Bring workflow loading and typed config behavior in line with
the spec and the Jira/Claude extension profile.

**Acceptance criteria:**

- Workflow front matter is optional. If absent, the whole file is the prompt and
config defaults are applied where possible.
- Workflow path default remains `./WORKFLOW.md`; explicit paths are respected.
- Prompt body is trimmed consistently.
- Unknown prompt variables fail rendering; unsupported filters fail clearly if
filter syntax is introduced.
- `workspace.root` supports `~`, `$VAR`, and relative paths resolved relative to
the selected workflow file.
- `hooks.after_create`, `hooks.before_run`, `hooks.after_run`,
`hooks.before_remove`, and `hooks.timeout_ms` are top-level config fields, not
`workspace.hooks`.
- Runtime getters exist for active states, terminal states, polling interval,
global concurrency, per-state concurrency, max turns, retry backoff cap, hook
timeout, provider command, and provider-specific timeouts.
- Defaults align with the spec or are documented in the Jira/Claude compliance
profile.
- Invalid config returns typed `ConfigValidationError` with clear field paths.

**Verification:**

- Extend `tests/test_workflow.py` for optional front matter, prompt trimming,
missing file, invalid YAML, and non-map front matter.
- Extend `tests/test_config.py` for every runtime getter, default, invalid type,
env path, and relative workspace root resolution.
- Add example validation tests for both `WORKFLOW.claude.md` and any minimal
no-front-matter workflow.
- Run `uv run pytest tests/test_workflow.py tests/test_config.py tests/test_examples.py`.

**Files likely touched:**

- `src/synphony/workflow.py`
- `src/synphony/config.py`
- `src/synphony/prompt.py`
- `tests/test_workflow.py`
- `tests/test_config.py`
- `tests/test_examples.py`
- `docs/examples/WORKFLOW.claude.md`
- `docs/ARCHITECTURE.md`

**Estimated scope:** Medium.

## Phase 2: Domain Model and Runtime State Alignment

**Description:** Close gaps between the current dataclasses and the spec's
logical model, while keeping provider-neutral names where Codex-specific fields
do not apply to Claude.

**Acceptance criteria:**

- `Issue` can represent Jira-normalized labels, blocker refs, URL, timestamps,
and optional branch metadata if Jira exposes it.
- Labels are normalized consistently, preferably lowercase per the spec.
- Blockers preserve enough information to determine whether blockers are
terminal, not just their identifiers, or the Jira limitation is documented and
enforced safely.
- `RunAttempt` carries enough metadata for retries and observability.
- `LiveSession` tracks provider-neutral session id, turn count, started time,
last event kind/message/time, usage totals when available, and provider.
- `RetryEntry` stores attempt, due time, identifier, reason/error, and backoff.
- Runtime state has a single authority for claimed, running, retrying, completed,
rate-limit, usage, and runtime accounting.

**Verification:**

- Extend `tests/test_models.py` for normalization and provider-neutral session
metadata.
- Update orchestrator and logging tests to use the richer runtime state.
- Run `uv run pytest tests/test_models.py tests/test_orchestrator.py tests/test_logging.py`.

**Files likely touched:**

- `src/synphony/models.py`
- `src/synphony/orchestrator.py`
- `src/synphony/logging.py`
- `tests/test_models.py`
- `tests/test_orchestrator.py`
- `tests/test_logging.py`

**Estimated scope:** Medium.

## Phase 3: Jira Tracker Production Readiness

**Description:** Harden the Jira `acli` adapter so it satisfies the tracker
contract for real production use, not only fixture parsing.

**Acceptance criteria:**

- Candidate fetch applies configured active states and bounded pagination.
- `fetch_issues_by_states([])` returns `[]` without invoking `acli`.
- `fetch_issue_states_by_ids()` supports reconciliation needs and returns enough
information to update running issue snapshots, or a separate issue-refresh
method is added and documented.
- Jira status names are normalized consistently against active and terminal
workflow states.
- Jira labels are normalized consistently.
- Jira blocker links are mapped to normalized blocker refs where possible.
- `acli` command failures, missing binary, timeouts, invalid JSON, missing fields,
and pagination integrity errors have typed error categories.
- Authenticated command discovery is captured in docs with sanitized sample
outputs for the target Jira site.
- The adapter never logs secrets or large raw Jira payloads by default.

**Verification:**

- Expand `tests/test_jira_acli.py` for pagination, empty state list, malformed
payloads, timeout mapping, lowercased labels, blocker variants, and
state-refresh behavior.
- Add or update sanitized fixtures under `tests/fixtures/acli/`.
- Add a skipped-by-default integration test profile requiring explicit
environment enablement and safe test JQL.
- Run `uv run pytest tests/test_jira_acli.py`.
- Manual smoke command:
  ```bash
  acli jira workitem search --jql '<safe test JQL>' --limit 1 --json
  ```

**Files likely touched:**

- `src/synphony/tracker/jira_acli.py`
- `src/synphony/tracker/base.py`
- `tests/test_jira_acli.py`
- `tests/fixtures/acli/`
- `docs/ARCHITECTURE.md`
- `README.md`

**Estimated scope:** Medium.

## Phase 4: Workspace Safety and Hook Semantics

**Description:** Bring workspace behavior fully in line with the spec's safety
and hook failure semantics.

**Acceptance criteria:**

- Workspace root and workspace path are normalized to absolute paths before use.
- Workspace key sanitization matches the documented policy. If strict spec
conformance is required, replace disallowed characters with `_` and allow only
`[A-Za-z0-9._-]`; otherwise document the current lowercase-hyphen policy as an
intentional implementation choice and adjust examples/tests.
- Existing non-directory paths at workspace locations fail safely.
- `after_create` failure aborts workspace creation.
- `before_run` failure aborts the current attempt.
- `after_run` failure is logged and ignored.
- `before_remove` failure is logged and ignored; cleanup still proceeds.
- Hook timeout uses top-level `hooks.timeout_ms`, defaulting to `60000`.
- Agent launch validates `cwd == workspace.path` and that workspace path remains
under root immediately before starting the subprocess.

**Verification:**

- Extend `tests/test_workspace.py` for non-directory collision, `after_run`
ignored failures, `before_remove` ignored failures, timeout config, and launch
preflight helper if added.
- Run `uv run pytest tests/test_workspace.py tests/test_agent_runner.py`.

**Files likely touched:**

- `src/synphony/workspace.py`
- `src/synphony/path_safety.py`
- `src/synphony/agent_runner.py`
- `tests/test_workspace.py`
- `tests/test_agent_runner.py`

**Estimated scope:** Medium.

## Phase 5: Claude Code Provider Contract and Backend

**Description:** Implement Claude Code as a production provider extension with a
documented, tested subprocess contract.

**Acceptance criteria:**

- Document the official or locally verified Claude Code CLI command form for
non-interactive execution.
- Document stdout/stderr behavior, structured output if available, exit-code
semantics, resume/session behavior, timeout behavior, approval handling,
sandbox posture, and user-input-required handling.
- `ClaudeBackend` implements `AgentBackend`.
- First turns run from the per-issue workspace as `cwd`.
- Continuation turns resume the same Claude session when supported. If the CLI
cannot support true continuation, the backend fails clearly and the limitation
is reflected in service policy.
- The backend emits normalized `AgentEvent` values for session start, turn start,
notifications/output, completion, failure, timeout, user input required, and
malformed output where applicable.
- A run cannot stall indefinitely on approvals or user input.
- Token/usage/rate-limit extraction is implemented if Claude exposes it; if not,
null usage is accepted and documented.
- Missing executable, nonzero exit, timeout, malformed output, and interrupted
process paths map to typed errors/events.

**Verification:**

- Add `tests/test_claude_backend.py` with mocked subprocess tests for success,
failure, timeout, missing executable, structured output parsing, and
continuation.
- Add sanitized fixtures under `tests/fixtures/claude/` if structured output is
available.
- Add a skipped-by-default real Claude smoke test using a harmless prompt in a
temporary workspace.
- Run `uv run pytest tests/test_claude_backend.py tests/test_agent_runner.py`.

**Files likely touched:**

- `src/synphony/agents/claude.py`
- `src/synphony/agents/registry.py`
- `src/synphony/errors.py`
- `tests/test_claude_backend.py`
- `tests/fixtures/claude/`
- `docs/ARCHITECTURE.md`
- `README.md`

**Estimated scope:** Medium to large, depending on the Claude CLI contract.

## Phase 6: Agent Runner Production Behavior

**Description:** Make `AgentRunner` a production worker component whose behavior
matches the spec's workspace, prompt, turn loop, hook, timeout, and failure
semantics.

**Acceptance criteria:**

- Creates or reuses the per-issue workspace.
- Runs `before_run` before each attempt and always runs `after_run` best-effort
after each attempt.
- Builds the first prompt from the workflow template.
- Sends continuation-only guidance after successful turns when the issue remains
active.
- Re-checks issue state after each successful turn.
- Stops at `agent.max_turns`.
- Distinguishes inactive, max turns, agent failure, timeout, prompt failure,
hook failure, and state-refresh failure.
- Forwards every provider event to the orchestrator callback.
- Stops provider sessions reliably in `finally` paths.

**Verification:**

- Expand `tests/test_agent_runner.py` for hook best-effort semantics, prompt
render failures, backend exceptions, state refresh failure, max-turn behavior,
and continuation event forwarding.
- Run `uv run pytest tests/test_agent_runner.py tests/test_agent_fakes.py`.

**Files likely touched:**

- `src/synphony/agent_runner.py`
- `src/synphony/agents/base.py`
- `tests/test_agent_runner.py`
- `tests/fakes.py`

**Estimated scope:** Medium.

## Phase 7: Orchestrator Service Loop, Retries, and Reconciliation

**Description:** Move from isolated orchestration methods to a production
long-running scheduler with single-authority runtime state.

**Acceptance criteria:**

- Startup validates config, configures logging, performs terminal workspace
cleanup, starts workflow reload, and schedules an immediate tick.
- Each tick reconciles active runs before dispatch.
- Dispatch preflight validation runs before candidate fetch.
- Candidate fetch errors skip dispatch for that tick and keep the service alive.
- Candidate sorting follows priority, created time, and identifier.
- Eligibility checks active state, terminal state, claimed, running, retrying,
blockers, global concurrency, and per-state concurrency.
- Blocker behavior is correct for Jira. If the spec's `Todo`-only rule is not
appropriate, document the Jira mapping and implement the chosen policy.
- Worker runs are launched concurrently enough for the orchestrator to track and
stop live sessions.
- Normal worker exit schedules a short continuation retry.
- Abnormal worker exit schedules exponential backoff using
`agent.max_retry_backoff_ms`.
- Retry timers re-fetch active candidates and dispatch only when still eligible.
- Slot exhaustion requeues retries with an explicit reason.
- Stall detection uses provider-neutral last event timestamps.
- Terminal tracker state stops sessions and cleans workspaces.
- Non-active tracker state stops sessions without cleanup.
- State-refresh failure keeps workers running and retries next tick.

**Verification:**

- Expand `tests/test_orchestrator.py` for tick sequencing, normal exit
continuation retry, abnormal exit backoff, retry timer behavior, slot
exhaustion, startup cleanup, state snapshot updates, and tracker error
handling.
- Add deterministic fake worker/session tests without real subprocesses.
- Run `uv run pytest tests/test_orchestrator.py tests/test_tracker_memory.py`.

**Files likely touched:**

- `src/synphony/orchestrator.py`
- `src/synphony/workflow_store.py`
- `src/synphony/models.py`
- `tests/test_orchestrator.py`
- `tests/test_workflow_store.py`

**Estimated scope:** Large. Split into smaller PRs.

## Phase 8: CLI and Host Lifecycle

**Description:** Replace the disabled run mode with a production host process
that starts and stops the orchestrator cleanly.

**Acceptance criteria:**

- `synphony <WORKFLOW.md>` starts the production service.
- No positional workflow path defaults to `./WORKFLOW.md`.
- `--check` remains a validation-only path.
- `--once` may be added as a clearly documented smoke-test helper but is not the
production path.
- Startup failures are operator-visible and return nonzero exit codes.
- SIGINT/SIGTERM trigger graceful shutdown: stop dispatch, stop active sessions
according to provider support, run best-effort cleanup hooks where appropriate,
flush logs, and exit cleanly.
- `--logs-root` continues to configure structured file logs.
- `--port` remains reserved unless the optional HTTP server is implemented.

**Verification:**

- Expand `tests/test_cli.py` for production startup composition using fakes,
missing workflow, invalid config, graceful shutdown hooks, `--check`, and
optional `--once`.
- Add manual smoke commands in `README.md`.
- Run `uv run pytest tests/test_cli.py`.

**Files likely touched:**

- `src/synphony/cli.py`
- `src/synphony/logging.py`
- `README.md`
- `tests/test_cli.py`

**Estimated scope:** Medium.

## Phase 9: Observability and Operator Safety

**Description:** Ensure production operators can understand failures and that
logs contain the context required by the spec.

**Acceptance criteria:**

- Structured logs include `issue_id`, `issue_identifier`, `session_id`,
`provider`, failure reason, and workspace path where relevant.
- Startup, validation, dispatch, tracker, workspace, agent, retry, and shutdown
failures are operator-visible.
- Logging sink setup failures do not crash orchestration when another sink can
still report the warning.
- Agent usage and rate-limit totals are accumulated if the provider exposes
them.
- Human-readable event summaries, if added, remain observability-only.
- The project documents its trust boundary, approval policy, sandbox policy, and
user-input-required behavior for Claude Code.

**Verification:**

- Extend `tests/test_logging.py` for required context fields and sink failure
behavior.
- Add orchestrator tests for event/usage aggregation if implemented.
- Run `uv run pytest tests/test_logging.py tests/test_orchestrator.py`.

**Files likely touched:**

- `src/synphony/logging.py`
- `src/synphony/orchestrator.py`
- `src/synphony/models.py`
- `tests/test_logging.py`
- `tests/test_orchestrator.py`
- `docs/ARCHITECTURE.md`
- `README.md`

**Estimated scope:** Medium.

## Phase 10: Integration Profile, CI, and Release Gate

**Description:** Add a repeatable production validation profile that proves Jira
and Claude work together without requiring credentials in normal unit tests.

**Acceptance criteria:**

- Unit tests remain hermetic and require no `acli`, Jira site, or Claude CLI.
- Integration tests are skipped by default and require explicit opt-in.
- Integration tests validate:
  - authenticated `acli` candidate query against safe JQL;
  - workspace creation under an isolated root;
  - Claude Code execution against a harmless test ticket/prompt;
  - no-candidate behavior;
  - failure behavior for missing Claude or `acli`.
- CI runs unit tests, Ruff, format check, and mypy on every change.
- Optional/manual CI job can run real integration tests with approved
credentials and a safe test Jira project.
- README documents setup, auth, safe test workflow, run commands, and production
limitations.

**Verification:**

- Add `tests/test_integration_jira_claude.py` with skip conditions.
- Add CI workflow for unit quality gates.
- Run:
  ```bash
  uv run pytest
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy
  SYNPHONY_INTEGRATION=1 uv run pytest tests/test_integration_jira_claude.py
  ```

**Files likely touched:**

- `tests/test_integration_jira_claude.py`
- `.github/workflows/ci.yml` or the repository's chosen CI path
- `README.md`
- `docs/examples/WORKFLOW.claude.md`

**Estimated scope:** Medium.

## Recommended Implementation Order

1. Record the Jira/Claude compliance profile and resolve open provider-policy
  decisions.
2. Fix workflow/config schema and examples.
3. Fix workspace hook semantics and path policy.
4. Harden Jira tracker behavior and fixtures.
5. Implement the Claude Code backend.
6. Strengthen the agent runner against real backend failures.
7. Rework orchestrator into the production service loop with retries and
  concurrent workers.
8. Wire the CLI host lifecycle.
9. Finish observability and operator safety docs.
10. Add integration profile and CI/release gates.

## Checkpoints

### Checkpoint A: Config and Workspace Foundation

- Workflow/config tests pass.
- Workspace tests pass.
- Example Claude workflow validates.
- Architecture doc states the Jira/Claude compliance profile.

### Checkpoint B: Real Integrations Ready

- Jira adapter has pagination/error/fixture coverage.
- Claude backend has subprocess fixture coverage.
- Agent runner handles backend failures and continuation policy.

### Checkpoint C: Production Service Ready

- CLI starts a long-running service.
- Orchestrator owns runtime state, dispatch, reconciliation, retries, and
shutdown.
- Structured logs expose startup, dispatch, worker, retry, and shutdown events.

### Checkpoint D: Release Candidate

- Full unit quality gate passes.
- Real Jira + Claude integration profile passes in an isolated test workflow.
- README and architecture docs describe setup, safety posture, limitations, and
production run commands.

## Open Questions to Resolve Before Coding Claude Production Support

- What is the canonical headless Claude Code command and output mode?
- Does Claude Code support a stable resume/session identifier suitable for
continuation turns?
- Can Claude Code expose token usage or rate-limit information?
- What approval and sandbox mode should production use?
- How should user-input-required events be surfaced or failed?
- Should Jira blocker handling be strict for all active states or mapped to a
configured Jira status equivalent of `Todo`?
- Is strict upstream conformance required, including Codex support, or is the
Jira/Claude profile the production conformance target for this repository?

