# Implementation Plan: Execute `tasks.md`

## Overview

Build `synphony-py` as a Python port of Symphony using `../symphony/SPEC.md` and the Elixir implementation under `../symphony/elixir/lib/` as references. The first usable milestone keeps the core Symphony behavior but adapts the tracker to Jira via `acli` and supports exactly two agent backends: Codex app-server and Claude Code CLI.

The implementation should proceed in small vertical slices. Each phase below leaves the repo in a testable state and avoids implementing future providers such as Copilot, Pi.dev, or OpenCode.

## Architecture Decisions

- Use a `src/synphony/` package layout with `pytest`, `ruff`, and a Python type checker configured from `pyproject.toml`.
- Use typed Python models consistently, preferably dataclasses unless early validation needs justify pydantic.
- Keep orchestration provider-agnostic through an `AgentBackend` protocol plus a provider registry.
- Keep tracker access behind a tracker interface; production Jira uses `acli`, tests use an in-memory tracker.
- Treat HTTP dashboard support as optional polish after the CLI, workflow loader, tracker, workspace, agent runner, and orchestrator are usable.

## Dependency Graph

Project bootstrap
  -> domain models and shared errors
  -> workflow/config loader
  -> tracker and workspace interfaces
  -> agent backend protocol
  -> fake tracker/backend tests
  -> orchestrator loop
  -> real Jira/Codex/Claude adapters
  -> CLI, logging, packaging, CI

Spike dependencies:

- `acli` command discovery must happen before the Jira adapter is finalized.
- Claude Code CLI discovery must happen before the Claude backend contract is finalized.
- Codex app-server can follow the SPEC and Elixir reference earlier than Claude.

## Phase 0: Confirm Scope and Bootstrap

### Task 0.1: Reconcile SPEC With Jira and Multi-Backend Scope

**Description:** Read the SPEC sections called out by `tasks.md` and record the implementation-specific reinterpretations for Jira and agent providers.

**Acceptance criteria:**

- Jira replaces Linear in tracker behavior and examples.
- Codex remains SPEC-aligned.
- Claude support is documented as a first-class v1 backend.
- Future providers are documented as reserved, not implemented.

**Verification:**

- Design notes mention Jira, Codex, Claude, and future provider boundaries.
- Open questions from `tasks.md` are either answered or explicitly carried forward.

**Dependencies:** None

**Files likely touched:** `docs/ARCHITECTURE.md`, `tasks.md`

**Estimated scope:** S

### Task 0.2: Bootstrap Python Project

**Description:** Create the initial Python package, test layout, tooling, README, and ignore rules.

**Acceptance criteria:**

- `pyproject.toml` defines package metadata, console script, runtime dependencies, and dev dependencies.
- `src/synphony/` and `tests/` exist.
- Ruff, type checking, and pytest can run on an empty/minimal package.
- README documents `acli`, Codex, and Claude CLI prerequisites.

**Verification:**

- `pytest`
- `ruff check .`
- `ruff format --check .`
- Type checker command selected in `pyproject.toml`

**Dependencies:** Task 0.1

**Files likely touched:** `pyproject.toml`, `.gitignore`, `README.md`, `src/synphony/__init__.py`, `tests/`

**Estimated scope:** S

### Checkpoint: Bootstrap

- Tooling runs cleanly.
- README documents install and provider prerequisites.
- Architecture notes capture implementation-defined choices.

## Phase 1: Models, Errors, and Workflow Loading

### Task 1.1: Implement Domain Models and Error Taxonomy

**Description:** Add typed models for issues, workflows, workspaces, run attempts, sessions, retries, runtime state, normalized agent events, and shared errors.

**Acceptance criteria:**

- Models cover the SPEC concepts needed by workflow, tracker, workspace, agent runner, and orchestrator code.
- Jira/acli errors and provider-agnostic agent errors are represented.
- Normalization helpers handle workspace keys, state comparisons, and session ids.

**Verification:**

- Unit tests for normalization helpers and representative model construction.
- Type checker passes for the model package.

**Dependencies:** Task 0.2

**Files likely touched:** `src/synphony/models.py`, `src/synphony/errors.py`, `tests/test_models.py`

**Estimated scope:** S

### Task 1.2: Implement Workflow and Config Loader

**Description:** Load `WORKFLOW.md` with YAML front matter and strict prompt templating, then expose typed config getters and validation.

**Acceptance criteria:**

- Missing workflow, invalid YAML, non-map front matter, unknown template variables, and invalid provider/tracker config fail clearly.
- `tracker.kind: jira` is the canonical tracker value.
- `agent.provider` supports `codex` and `claude`.
- Provider-specific config blocks are validated only for the selected provider.

**Verification:**

- Unit tests cover parse success, parse failures, strict template failures, defaults, env var resolution, and provider selection.
- Type checker and ruff pass.

**Dependencies:** Task 1.1

**Files likely touched:** `src/synphony/workflow.py`, `src/synphony/config.py`, `src/synphony/prompt.py`, `tests/test_workflow.py`, `tests/test_config.py`

**Estimated scope:** M

### Task 1.3: Add Dynamic Workflow Reload

**Description:** Watch or poll `WORKFLOW.md` for changes and keep the last good config when reload fails.

**Acceptance criteria:**

- Reload detects changed content.
- Invalid reload logs an error and keeps the last good workflow.
- Poll/watch implementation can be tested deterministically.

**Verification:**

- Unit tests with temporary workflow files.
- Manual smoke test by editing a sample workflow.

**Dependencies:** Task 1.2

**Files likely touched:** `src/synphony/workflow_store.py`, `tests/test_workflow_store.py`

**Estimated scope:** M

### Checkpoint: Workflow Foundation

- Workflow parse, config validation, and prompt rendering tests pass.
- Provider selection and Jira tracker config are documented in examples or README.

## Phase 2: Tracker and Workspace Foundation

### Task 2.1: Implement Tracker Interface and Memory Tracker

**Description:** Define the tracker protocol used by the orchestrator and add an in-memory implementation for tests.

**Acceptance criteria:**

- Tracker exposes candidate fetch, state fetch by names, and state fetch by ids.
- Memory tracker can model active, inactive, terminal, blocked, and priority cases.

**Verification:**

- Unit tests for memory tracker behavior.
- Orchestrator tests can use memory tracker without network or `acli`.

**Dependencies:** Task 1.1

**Files likely touched:** `src/synphony/tracker/base.py`, `src/synphony/tracker/memory.py`, `tests/test_tracker_memory.py`

**Estimated scope:** S

### Task 2.2: Spike `acli` and Define Jira Mapping

**Description:** Discover stable non-interactive `acli` commands for listing/searching issues, fetching fields, pagination, and issue links.

**Acceptance criteria:**

- Notes include commands, sample sanitized outputs, JSON availability, pagination behavior, and blocker/link support.
- Active and terminal workflow states are mapped to Jira status names with case-insensitive normalization.
- Open questions in `tasks.md` are updated or answered.

**Verification:**

- Re-run documented `acli` commands against the authenticated environment.
- Sanitized fixtures are ready for parser tests.

**Dependencies:** Task 0.1

**Files likely touched:** `docs/ARCHITECTURE.md`, `tests/fixtures/acli/`, `tasks.md`

**Estimated scope:** M

### Task 2.3: Implement Jira `acli` Tracker

**Description:** Add a production tracker adapter that invokes `acli`, parses output, maps fields into `Issue`, handles pagination, and maps errors.

**Acceptance criteria:**

- Adapter supports all tracker protocol operations.
- Subprocess calls have timeouts.
- Parser prefers structured output and has fixture coverage.
- Jira blockers are represented in the normalized issue model if supported by `acli`.

**Verification:**

- Unit tests with sanitized `acli` fixtures.
- Integration test marker for optional real Jira calls.

**Dependencies:** Tasks 2.1, 2.2

**Files likely touched:** `src/synphony/tracker/jira_acli.py`, `tests/test_jira_acli.py`, `tests/fixtures/acli/`

**Estimated scope:** M

### Task 2.4: Implement Workspace Manager and Path Safety

**Description:** Create/reuse per-issue workspaces, enforce root safety, and run lifecycle hooks.

**Acceptance criteria:**

- Workspace paths are deterministic and cannot escape the configured root.
- Hooks run with the workspace as `cwd`, configured shell, and timeout.
- Startup terminal cleanup can delete terminal-state workspaces best-effort.

**Verification:**

- Unit tests for path safety, create/reuse behavior, hook success/failure/timeout, and cleanup.

**Dependencies:** Task 1.2

**Files likely touched:** `src/synphony/path_safety.py`, `src/synphony/workspace.py`, `tests/test_workspace.py`

**Estimated scope:** M

### Checkpoint: Tracker and Workspace

- Memory tracker and workspace tests pass.
- Jira parser fixture tests pass.
- No real `acli` dependency in unit tests.

## Phase 3: Agent Backend Boundary

### Task 3.1: Implement Agent Backend Protocol and Registry

**Description:** Define the backend interface for all providers and a registry/factory keyed by `agent.provider`.

**Acceptance criteria:**

- Protocol supports session start/stop, first turn, continuation turn, normalized event callbacks, and timeout inputs.
- Registry supports `codex` and `claude`.
- Future provider ids are documented but not implemented.

**Verification:**

- Unit tests for registry dispatch and unsupported provider errors.
- Fake backend can be used in orchestrator tests.

**Dependencies:** Task 1.1

**Files likely touched:** `src/synphony/agents/base.py`, `src/synphony/agents/registry.py`, `tests/test_agent_registry.py`

**Estimated scope:** S

### Task 3.2: Implement Fake Agent Backend for Tests

**Description:** Add a deterministic backend that emits normalized events and controllable failures/timeouts for orchestrator tests.

**Acceptance criteria:**

- Fake backend can simulate success, failure, stall, continuation, and stop behavior.
- Events include provider id and normalized session/turn ids.

**Verification:**

- Unit tests for fake backend scenarios.

**Dependencies:** Task 3.1

**Files likely touched:** `tests/fakes.py`, `tests/test_agent_fakes.py`

**Estimated scope:** S

### Checkpoint: Testable Core Boundary

- Tracker, workspace, workflow, and agent backend boundaries are testable without external CLIs.
- Fake implementations are ready for orchestrator development.

## Phase 4: Orchestrator Core

### Task 4.1: Implement Prompt Builder and Shared Agent Runner

**Description:** Build prompts from issue/workflow/attempt context and implement the provider-agnostic runner loop that manages workspace hooks, backend calls, continuation turns, and event forwarding.

**Acceptance criteria:**

- First and continuation prompts follow SPEC intent.
- Runner delegates all provider-specific behavior to `AgentBackend`.
- Hooks run in the correct order around agent turns.
- Max turns and inactive issue checks are enforced.

**Verification:**

- Unit tests with memory tracker, fake workspace hooks, and fake backend.

**Dependencies:** Tasks 1.2, 2.4, 3.2

**Files likely touched:** `src/synphony/prompt.py`, `src/synphony/agent_runner.py`, `tests/test_prompt.py`, `tests/test_agent_runner.py`

**Estimated scope:** M

### Task 4.2: Implement Orchestrator Dispatch and Runtime State

**Description:** Port the scheduler decisions for polling, sorting, concurrency caps, claims, running sessions, and retry queues.

**Acceptance criteria:**

- Candidate issues dispatch by priority, creation time, then identifier.
- Global and per-state concurrency caps are enforced.
- Blocked issues are not dispatched.
- Runtime state is the single authority for claimed/running/retry status.

**Verification:**

- Unit tests for dispatch ordering, concurrency, blockers, duplicate claims, and retry queue behavior.

**Dependencies:** Task 4.1

**Files likely touched:** `src/synphony/orchestrator.py`, `tests/test_orchestrator.py`

**Estimated scope:** M

### Task 4.3: Implement Reconciliation, Stall Detection, and Cleanup

**Description:** Refresh tracker state for running issues, stop inactive/terminal runs, clean terminal workspaces, and detect stalled sessions using last event timestamps.

**Acceptance criteria:**

- Terminal issue states stop runs and clean workspaces.
- Inactive issue states stop runs without terminal cleanup.
- Stalled sessions move to retry/failure according to config.
- Startup cleanup handles terminal-state issues.

**Verification:**

- Unit tests for terminal transition, inactive transition, stalled backend, startup cleanup, and retry backoff.

**Dependencies:** Task 4.2

**Files likely touched:** `src/synphony/orchestrator.py`, `tests/test_orchestrator_reconciliation.py`

**Estimated scope:** M

### Checkpoint: Core Orchestrator

- All core behavior works with memory tracker and fake agent backend.
- No Codex, Claude, or Jira process is required for unit tests.
- Retry, reconciliation, cleanup, and stall behavior are covered.

## Phase 5: Real Agent Backends

### Task 5.1: Implement Codex App-Server Backend

**Description:** Port the Codex app-server protocol from the SPEC and Elixir reference, including JSON-line communication, session startup, events, usage, rate limits, and timeouts.

**Acceptance criteria:**

- Backend launches `bash -lc <codex.command>` in the workspace.
- Protocol stream and stderr are handled separately.
- Thread/turn/session ids and usage fields normalize into `AgentEvent`.
- Approval and sandbox options are passed through according to config.

**Verification:**

- Protocol tests with mocked stdin/stdout fixtures.
- Optional integration test gated behind environment/profile.

**Dependencies:** Task 3.1

**Files likely touched:** `src/synphony/agents/codex.py`, `tests/test_codex_backend.py`, `tests/fixtures/codex/`

**Estimated scope:** M

### Task 5.2: Spike Claude Code CLI Contract

**Description:** Identify the official headless Claude Code CLI interface and document session, turn, streaming, timeout, approval, and output semantics.

**Acceptance criteria:**

- Notes include command lines, `--help` or official docs references, stdout/stderr behavior, resume/session behavior, and unsupported SPEC concepts.
- Implementation contract for `ClaudeBackend` is approved before coding.

**Verification:**

- Re-run documented CLI smoke commands locally.
- Tests fixtures can be designed from captured sanitized output.

**Dependencies:** Task 0.1

**Files likely touched:** `docs/ARCHITECTURE.md`, `tests/fixtures/claude/`, `tasks.md`

**Estimated scope:** M

### Task 5.3: Implement Claude Code CLI Backend

**Description:** Implement Claude as an `AgentBackend` using the discovered subprocess contract and normalize output into shared events.

**Acceptance criteria:**

- First and continuation turns work from a workspace `cwd`.
- Output streaming or polling emits normalized events.
- Timeouts are enforced orchestrator-side if the CLI lacks native stall signals.
- Approval/user-input-required behavior cannot hang the orchestrator indefinitely.

**Verification:**

- Mock subprocess tests for success, failure, timeout, and continuation.
- Optional integration test gated behind environment/profile.

**Dependencies:** Tasks 3.1, 5.2

**Files likely touched:** `src/synphony/agents/claude.py`, `tests/test_claude_backend.py`, `tests/fixtures/claude/`

**Estimated scope:** M

### Task 5.4: Implement Optional Jira Dynamic Tool for Codex

**Description:** Port the SPEC dynamic tool concept from Linear GraphQL to a constrained Jira `acli` tool for Codex sessions when supported and configured.

**Acceptance criteria:**

- Tool is advertised only for compatible provider/tracker combinations.
- Allowed `acli` operations are constrained and documented.
- Claude omission is documented unless the CLI supports custom tools.

**Verification:**

- Unit tests for tool availability rules and command constraints.
- Protocol fixture test for Codex tool advertisement.

**Dependencies:** Tasks 2.3, 5.1

**Files likely touched:** `src/synphony/agents/codex.py`, `src/synphony/tools/jira_acli.py`, `tests/test_jira_tool.py`

**Estimated scope:** M

### Checkpoint: Real Backends

- Codex protocol tests pass.
- Claude subprocess tests pass.
- Optional integrations are marked and skipped by default.
- Provider selection works end to end through config.

## Phase 6: CLI, Logging, and Operator Surface

### Task 6.1: Implement CLI Entrypoint

**Description:** Add the `synphony` CLI that loads workflow config, validates startup, starts the orchestrator, and handles shutdown.

**Acceptance criteria:**

- Positional workflow path defaults to `./WORKFLOW.md`.
- Startup validation fails clearly with nonzero exit codes.
- SIGINT/SIGTERM trigger graceful shutdown.
- Flags include `--logs-root` and `--port` if HTTP is enabled.

**Verification:**

- CLI unit tests with `pytest`.
- Manual smoke test against a sample workflow using memory/fake components if supported.

**Dependencies:** Tasks 4.3, 5.1, 5.3

**Files likely touched:** `src/synphony/cli.py`, `tests/test_cli.py`, `pyproject.toml`

**Estimated scope:** M

### Task 6.2: Implement Structured Logging

**Description:** Emit operator-friendly logs with issue, workspace, session, provider, retry, and lifecycle context.

**Acceptance criteria:**

- Logs include `issue_id`, `issue_identifier`, `session_id`, and `provider` when applicable.
- File logging works when `--logs-root` is set.
- Errors preserve structured codes from the error taxonomy.

**Verification:**

- Unit tests for log context formatting.
- Manual smoke test writes logs under a temporary root.

**Dependencies:** Tasks 1.1, 6.1

**Files likely touched:** `src/synphony/logging.py`, `tests/test_logging.py`

**Estimated scope:** S

### Task 6.3: Add Optional HTTP Status Surface

**Description:** Implement the optional dashboard/API only after the core daemon path is usable.

**Acceptance criteria:**

- `/api/v1/state`, `/api/v1/<issue_identifier>`, and `POST /api/v1/refresh` expose runtime state if implemented.
- HTTP is optional and disabled unless configured or requested.
- No core behavior depends on the HTTP server.

**Verification:**

- API tests with in-memory orchestrator state.
- Manual smoke test if enabled.

**Dependencies:** Task 6.2

**Files likely touched:** `src/synphony/http.py`, `tests/test_http.py`

**Estimated scope:** M

### Checkpoint: Usable CLI

- CLI starts, validates config, and shuts down cleanly.
- Logs provide enough context to debug a run.
- Optional HTTP work does not block first usable release.

## Phase 7: Examples, CI, and Release Readiness

### Task 7.1: Add Workflow Examples

**Description:** Provide minimal Codex and Claude `WORKFLOW.md` examples with Jira tracker config.

**Acceptance criteria:**

- Examples document `tracker.kind: jira`, active/terminal states, workspace root, hooks, and provider-specific blocks.
- Codex and Claude examples are distinct and runnable after prerequisites are installed.

**Verification:**

- Example workflows parse in tests.
- README links to both examples.

**Dependencies:** Tasks 1.2, 5.3

**Files likely touched:** `docs/examples/WORKFLOW.codex.md`, `docs/examples/WORKFLOW.claude.md`, `README.md`, `tests/test_examples.py`

**Estimated scope:** S

### Task 7.2: Add CI

**Description:** Configure CI to run formatting checks, linting, type checking, and unit tests on each push.

**Acceptance criteria:**

- CI does not require real Jira, Codex, or Claude credentials.
- Integration tests are opt-in via markers or manual jobs.
- Dependency installation path is documented.

**Verification:**

- CI workflow passes locally if using an equivalent command.
- Default test suite skips integration tests.

**Dependencies:** Task 0.2

**Files likely touched:** `.github/workflows/ci.yml` or project CI equivalent, `pyproject.toml`, `README.md`

**Estimated scope:** S

### Task 7.3: Final Definition-of-Done Pass

**Description:** Validate the first usable milestone against `tasks.md` section 13 and update docs/open questions.

**Acceptance criteria:**

- Loads and hot-reloads `WORKFLOW.md`.
- Polls Jira via `acli`.
- Creates safe workspaces and runs hooks.
- Supports Codex and Claude through `AgentBackend`.
- Reconciles state transitions and cleans terminal workspaces.
- Emits structured logs.
- Future providers remain out of scope.

**Verification:**

- Full unit suite passes.
- Ruff and type checking pass.
- Optional integration smoke test is documented, and run if credentials/tools are available.

**Dependencies:** Tasks 7.1, 7.2

**Files likely touched:** `tasks.md`, `README.md`, `docs/ARCHITECTURE.md`

**Estimated scope:** S

### Checkpoint: First Usable Milestone

- `pytest`
- `ruff check .`
- `ruff format --check .`
- Type checker command
- Example workflows parse
- Optional real `acli` plus Codex/Claude smoke path documented

## Parallelization Opportunities

- Project bootstrap and SPEC/design reconciliation can happen in parallel after the Python version/package manager choice is made.
- Workflow/config tests can be developed in parallel with tracker and workspace tests once shared models exist.
- Jira `acli` spike and Claude CLI spike can run in parallel because they affect different adapters.
- Codex backend implementation can proceed while Claude CLI discovery is still underway.
- CI, README, and example workflow polish can proceed once CLI/config commands stabilize.

## Sequential Work

- Shared models and errors should land before workflow, tracker, workspace, and agent runner work.
- The `AgentBackend` protocol should land before either real backend.
- Orchestrator core should be proven with memory tracker and fake backend before wiring real Jira/Codex/Claude.
- Real integration tests should come after deterministic unit tests and fixtures exist.

## Risks and Mitigations


| Risk                                                       | Impact | Mitigation                                                                           |
| ---------------------------------------------------------- | ------ | ------------------------------------------------------------------------------------ |
| `acli` lacks stable JSON output for needed Jira fields     | High   | Spike first, capture fixtures, isolate parsing behind the Jira adapter               |
| Claude Code CLI has no reliable headless/session API       | High   | Spike before implementation, document gaps, keep timeout enforcement in orchestrator |
| Orchestrator complexity grows before boundaries are stable | High   | Build with memory tracker and fake backend first                                     |
| Future provider support bloats v1                          | Medium | Reserve config names only; do not implement third providers                          |
| Integration tests become flaky due to external services    | Medium | Keep unit tests fixture-based and mark integrations opt-in                           |


## Open Questions To Resolve During Spikes

- Which exact `acli` commands and flags are stable for non-interactive Jira issue listing, field reads, issue links, and pagination?
- What is the official Claude Code CLI machine interface for headless execution, continuation, and streaming?
- Should `agent.provider` be required, or should it default to `codex` for SPEC continuity?
- Should unused provider config blocks be ignored for forward compatibility or rejected to catch mistakes?
- Should Jira workflows use raw status names only, or status category plus status name?