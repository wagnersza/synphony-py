# synphony-py — migration and build tasks

This file tracks work to implement **Symphony** in Python (`synphony-py`), using `[../symphony/SPEC.md](../symphony/SPEC.md)` and the **Elixir reference** under `../symphony/elixir` as blueprints. Product differences from the published SPEC:

1. **Issue tracker: Jira** — integration via the **Atlassian CLI (`acli`)**, assumed **already authenticated** in the runtime environment (no Linear; no `LINEAR_API_KEY` flow).
2. **Coding agents: pluggable providers** — the orchestrator talks to a small **agent backend interface** (session, turns, streaming events, timeouts). **For the first implementation scope, support only two backends: OpenAI Codex (app-server, SPEC-aligned) and Anthropic Claude Code CLI.** Design the interface so **adding more CLIs later is straightforward**; do **not** implement those extra backends now.

**Future agent backends (document and design for; do not implement in the first pass):** GitHub Copilot CLI, Pi.dev, OpenCode, and any similar “headless” or scriptable coding-agent CLIs. Keep provider ids and config keys **namespaced** so new backends do not collide (e.g. `agent.provider: copilot` with a `copilot:` config block when the time comes).

Use this list as a backlog; reorder or split tasks as the team learns more from `acli`, `codex app-server`, and the Claude Code CLI.

---

## 0. Goals, scope, and references

- **0.1** Re-read `SPEC.md` and list any sections that must be **reinterpreted** for Jira + multiple agent backends (e.g. Section 11 “Linear” → Jira; client-side `linear_graphql` → Jira-oriented tool; Codex sections stay canonical for the **codex** provider).
- **0.2** Inventory the Elixir reference (`../symphony/elixir/lib/`) and map each area to a Python package/module (see section “Reference mapping” at the end).
- **0.3** Write a short **design note** in-repo (optional file name: `docs/ARCHITECTURE.md` only if you want it) describing: process model, threading/async model, how `acli` is invoked, and the **agent provider** boundary (orchestrator → `AgentBackend` → Codex vs Claude). *Skip if you prefer to keep only this file until implementation stabilizes.*
- **0.4** Align on **Python version** (e.g. 3.12+) and **package manager** (`uv` or `poetry` or `hatch`); document the choice in `pyproject.toml` / README when the project is bootstrapped.
- **0.5** **Agent provider extensibility (design only):** define a stable internal protocol: start/stop session, run turn, event stream → normalized `AgentEvent` (session id, turn id, usage, rate limits, errors). Document how **future** providers (Copilot, Pi.dev, OpenCode) would register without changing orchestrator logic. No code required beyond what Codex/Claude need; **no** Copilot/Pi/OpenCode implementation tasks in this milestone.

---

## 1. Repository and Python project setup

- **1.1** Add `pyproject.toml` with: project metadata, dependency groups (runtime / dev), console script entry point for the CLI (e.g. `synphony` or `synphony-py`).
- **1.2** Add strict-enough **tooling**: formatter (ruff format or black), linter (ruff), type checker (pyright or mypy), and a test runner (pytest).
- **1.3** Add `src/` layout (recommended: `src/synphony/`) and `tests/` with shared fixtures.
- **1.4** Add `.gitignore` for Python, venvs, caches, and local workspace roots.
- **1.5** Add a **minimal README** (install, `acli` login prerequisite, run command, link to SPEC, and how to pick **Codex vs Claude** in `WORKFLOW.md`).
- **1.6** Pin/document **runtime prerequisites** by provider: `acli` on `PATH` (always for Jira); for runs, `**codex`** on `PATH` when using the Codex backend, **Claude Code CLI** on `PATH` when using the Claude backend; shell used for hooks (`sh -lc` / `bash -lc` per SPEC).

---

## 2. Domain model and shared types

Port the conceptual model from **SPEC §4** and the Elixir structs/modules into typed Python (dataclasses or pydantic models — choose one and stay consistent).

- **2.1** `Issue`, `WorkflowDefinition`, service config view, `Workspace`, `RunAttempt`, `LiveSession`, `RetryEntry`, orchestrator runtime state — fields as in SPEC.
- **2.2** Normalization helpers: workspace key from issue identifier, lowercase state comparison, session id from thread/turn ids (provider-specific sources: Codex app-server vs Claude — same **normalized** `session_id` in logs and state).
- **2.3** Error taxonomy: mirror SPEC error classes where applicable; add Jira/acli-specific errors (`acli_not_found`, `jira_query_failed`, etc.); add **provider-agnostic** agent errors where useful (`agent_not_found`, `agent_protocol_error`, `agent_timeout`) plus provider-prefixed detail in logs.

---

## 2.A Agent provider abstraction (required for multi-backend)

- **2.A.1** Introduce an `**AgentBackend`** (or equivalent) interface used by `agent_runner`: same orchestration hooks for all providers (workspace `cwd`, first vs continuation prompt, max turns, event callback, timeouts).
- **2.A.2** **Factory/registry:** map `agent.provider` (or top-level `coding_agent.provider`) string → implementation module. Supported values in **v1**: `codex`, `claude`. Reserve documented **future** ids (implementation stub optional): e.g. `copilot`, `pi`, `opencode` — **do not implement**; only ensure naming and config layout **could** accommodate them (separate YAML blocks per provider).
- **2.A.3** Normalize raw provider events into **one internal event model** so the orchestrator and observability stay provider-agnostic (token fields optional if a CLI does not expose them).

---

## 3. Workflow loader and configuration layer

Align with **SPEC §5–6** and Elixir `workflow.ex`, `workflow_store.ex`, `config/schema.ex`, `config.ex`.

- **3.1** Load `WORKFLOW.md`: YAML front matter + Markdown body; errors for missing file, bad YAML, non-map front matter.
- **3.2** Implement **strict** prompt templating (SPEC recommends Liquid-compatible semantics): `issue`, `attempt`; unknown variables/filters fail.
- **3.3** Typed config getters with defaults and `**$VAR`** resolution for allowed keys; path expansion (`~`, env) per SPEC.
- **3.4** **Dynamic reload**: watch `WORKFLOW.md` (watchdog or periodic stat); on change re-apply config + template; invalid reload keeps last good config and logs loudly (SPEC §6.2).
- **3.5** Dispatch **preflight** validation: workflow parseable, tracker kind supported, agent command present, etc.

### 3.A Workflow schema changes for synphony-py

Keep **SPEC-compatible** `codex` settings when `agent.provider` is `codex`. Add **parallel** settings for Claude when `agent.provider` is `claude`. Tracker side: Jira instead of Linear; agent side: **select provider**, do not remove Codex.

- **3.A.1** Define `tracker.kind: jira` (or `atlassian` — pick one canonical string and document it).
- **3.A.2** Replace Linear fields with Jira-oriented fields, for example (exact names TBD with `acli` capabilities):
  - `tracker.project_key` or `tracker.jql` or `tracker.board_id` — **spike** which `acli` supports cleanly for “candidate issues”.
  - Optional `tracker.site_url` if `acli` needs explicit cloud host context.
  - **No API token** in workflow if auth is always via logged-in `acli`; if optional token/env is needed for some calls, keep behind `$VAR` and document as optional override.
- **3.A.3** **Agent provider selection** — add explicit workflow keys, for example:
  - `agent.provider`: `codex` | `claude` (required for dispatch once multiple backends exist).
  - **Codex path:** retain `**codex`** block per SPEC (`command` default `codex app-server`, `approval_policy`, `thread_sandbox`, `turn_sandbox_policy`, timeouts, etc.).
  - **Claude path:** add a `**claude`** block (names TBD): e.g. `command`, timeouts mirroring `read_timeout_ms` / `turn_timeout_ms` / `stall_timeout_ms` as closely as the CLI allows.
  - **Preflight:** validate the block that matches the selected provider; ignore or forbid unused provider blocks (pick one policy and document).
- **3.A.4** **Future providers (config only):** document placeholder shape for e.g. `copilot:`, `pi:`, `opencode:` sections — **no parsers beyond ignoring unknown keys** or strict reject — team choice; default recommendation is **ignore unknown top-level keys** per SPEC forward-compat, and reserve nested blocks under a future `providers:` map if preferred.
- **3.A.5** Update example `WORKFLOW.md`(s): one minimal **Codex** sample and one minimal **Claude** sample under `docs/` or repo root when ready.

---

## 4. Jira tracker client via `acli`

Replace Elixir `lib/symphony_elixir/linear/*` and `tracker.ex` with a **Jira adapter** that still exposes the **same three operations** as SPEC §11.1:

1. `fetch_candidate_issues()` — active workflow states, bounded pagination if applicable.
2. `fetch_issues_by_states(state_names)` — startup terminal cleanup.
3. `fetch_issue_states_by_ids(issue_ids)` — reconciliation for running issues.

Tasks:

- **4.1** **Spike `acli`**: enumerate commands for listing/searching issues, fetching by key/id, and field selection (status, summary, description, labels, priority, links/blockers, timestamps). Capture example JSON/text outputs in dev notes.
- **4.2** Define how **active** and **terminal** states from workflow YAML map to **Jira status names** (strings). Document normalization (case-insensitive).
- **4.3** Implement subprocess invocation of `acli` with timeouts, structured parsing of output (prefer JSON if `acli` supports `--json` or similar), and consistent error mapping.
- **4.4** Map Jira fields into the normalized `Issue` model; implement **blockers** per SPEC (Jira “blocks” link type or equivalent — confirm with acli/jira schema).
- **4.5** **Pagination**: if candidate queries can return many issues, implement bounded fetch consistent with SPEC spirit (page size ~50 if applicable).
- **4.6** Implement `**Memory` tracker** (see Elixir `tracker/memory.ex`) for unit tests — deterministic fake issues without network/`acli`.

---

## 5. Workspace manager and path safety

Port `workspace.ex` + `path_safety.ex`.

- **5.1** Compute workspace path: `<workspace.root>/<sanitized_identifier>`; enforce root prefix invariant.
- **5.2** Create/reuse directories; track `created_now` for `after_create` hook.
- **5.3** Hooks: `after_create`, `before_run`, `after_run`, `before_remove` — shell execution with `cwd` in workspace, timeout from config (SPEC §9.4).
- **5.4** Startup **terminal cleanup**: for terminal-state issues, delete workspace directories best-effort (SPEC §8.6).

---

## 6. Agent runners — shared orchestration + two backends (Codex + Claude Code)

Elixir reference: `codex/app_server.ex`, `agent_runner.ex`, `codex/dynamic_tool.ex`. In Python, `**agent_runner`** depends only on `**AgentBackend`**; concrete implementations live in separate modules.

**Shared (all providers):**

- **6.0** Implement `agent_runner` loop: create/reuse workspace, hooks, build prompt, delegate to `AgentBackend`, forward normalized events, continuation turns until max turns or inactive issue — same control flow as SPEC §16.5 (adapt names).

### 6.1 Codex (OpenAI) — app-server backend (**implement**)

Align with **SPEC §10** and the Elixir implementation (JSON-line / app-server protocol).

- **6.1.1** Subprocess: `bash -lc <codex.command>` (default `codex app-server`), `cwd` = workspace; stderr vs protocol stream separation per SPEC.
- **6.1.2** Session startup, thread/turn ids, token usage and rate-limit extraction, turn timeouts (`read_timeout_ms`, `turn_timeout_ms`), stall detection fed by last event time.
- **6.1.3** Pass-through for `approval_policy`, `thread_sandbox`, `turn_sandbox_policy` per installed Codex schema (SPEC §5.3.6).
- **6.1.4** **Dynamic tools:** port `**linear_graphql`** concept to `**jira_acli`** (or similar) when `tracker.kind == jira` — constrained `acli` execution for agent-side Jira operations; mirror Elixir `dynamic_tool` behavior and SPEC §10.5 extension pattern.

### 6.2 Claude Code CLI — backend (**implement**)

**Discovery phase (blocking for this backend):**

- **6.2.1** **Spike Claude Code CLI**: identify the supported **headless** flow (stdin/stdout protocol, JSON-RPC, file-based prompts, resume/session ids). Collect official docs or `--help` output in notes.
- **6.2.2** Map SPEC concepts → Claude: “thread”, “turn”, token usage — supported natively or **documented gaps** with simplified behavior.
- **6.2.3** Define subprocess contract: command line, `cwd` = workspace, env vars, stderr vs stdout separation.

**Implementation phase:**

- **6.2.4** Implement `ClaudeBackend`: session lifecycle, first turn + continuation turns with continuation-only guidance (SPEC §7.1, §10.2 analog).
- **6.2.5** Stream or poll output; **normalize** into the same internal events as Codex where possible.
- **6.2.6** Timeouts: read/turn/stall — stall enforced **orchestrator-side** from last event time if Claude lacks native stall signals.
- **6.2.7** Policy: approvals / user-input-required — defaults + docs (SPEC §10.5 spirit); must not stall forever.

### 6.3 Future agent CLIs (**do not implement now**)

Track as **follow-up epics** once the abstraction exists: **GitHub Copilot CLI**, **Pi.dev**, **OpenCode**, others. For each future backend, expect: spike CLI contract, new `agent.provider` value, provider-specific YAML block, implementation of `AgentBackend`, tests, README — **omit from current milestone scope**.

### 6.A Dynamic client-side tools (optional extension)

- **6.A.1** **Codex path:** Jira tool (`jira_acli` / constrained `acli`) advertised during session startup when applicable (SPEC §10.5 pattern).
- **6.A.2** **Claude path:** same tool **only if** Claude Code’s protocol supports custom tools; otherwise document omission.

---

## 7. Orchestrator, polling, retries, reconciliation

Port `orchestrator.ex` behavior and tests in `core_test.exs` / `orchestrator_status_test.exs`.

- **7.1** Single authoritative in-memory state: claimed/running/retry queues per SPEC §4.1.8.
- **7.2** Poll loop on `polling.interval_ms`; reschedule on config reload.
- **7.3** Dispatch sorting: priority → `created_at` → identifier (SPEC §8.2).
- **7.4** Concurrency: global + per-state caps (`agent.max_concurrent_agents_by_state`).
- **7.5** Blocker gating for `Todo`-equivalent state if retained (SPEC §8.2); clarify mapping to Jira status names in workflow config.
- **7.6** Retries: continuation delay (~1s) vs exponential backoff for failures; cap with `agent.max_retry_backoff_ms`.
- **7.7** Reconciliation: refresh tracker state for running issues; terminal → stop + cleanup; inactive → stop without cleanup (SPEC §8.5).
- **7.8** Stall detection using **last agent event** timestamps from the active provider (Codex or Claude) (SPEC §8.5 Part A).

---

## 8. Observability and optional HTTP dashboard

Port concepts from `log_file.ex`, `status_dashboard.ex`, `http_server.ex`, `symphony_elixir_web/`*.

- **8.1** Structured logging with required context fields (`issue_id`, `issue_identifier`, `session_id`).
- **8.2** Optional file logs / log root flag (mirror Elixir `--logs-root` if desired).
- **8.3** **Optional** HTTP server (SPEC §13.7): `/`, `/api/v1/state`, `/api/v1/<issue_identifier>`, `POST /api/v1/refresh` — use FastAPI/Starlette or similar if implementing.

---

## 9. CLI

Port `cli.ex` / `mix` tasks where relevant.

- **9.1** Positional workflow path or default `./WORKFLOW.md`; fail clearly if missing.
- **9.2** Flags: `--port` (if HTTP enabled), `--logs-root`, graceful shutdown on SIGINT/SIGTERM.
- **9.3** Exit codes: nonzero on startup validation failure.

---

## 10. Testing strategy

- **10.1** Unit tests: workflow parsing, config defaults, template strictness, workspace path rules, orchestrator decisions (use `Memory` tracker + fake agent runner).
- **10.2** Protocol tests: mock **Codex** app-server stdin/stdout (fixtures aligned with SPEC / Elixir tests); mock **Claude** subprocess per discovered CLI contract.
- **10.3** Golden/fixture tests for `acli` **output parsing** (record sanitized samples).
- **10.4** Optional integration profile: real `acli` + **either** real Codex **or** real Claude against a test Jira project — gated env vars, marked `@pytest.mark.integration`.

---

## 11. CI and packaging

- **11.1** GitHub Actions / GitLab CI: lint, typecheck, unit tests on each push.
- **11.2** Optional job for integration tests (manual approval or scheduled).
- **11.3** `pip install -e .` or `uv sync` documented; consider publishing internally if needed.

---

## 12. Migration checklist from Elixir reference

Use this as a feature parity checklist against `../symphony/elixir/lib/`:


| Elixir module                                  | Python target (suggested)                                               |
| ---------------------------------------------- | ----------------------------------------------------------------------- |
| `workflow.ex`, `workflow_store.ex`             | `synphony.workflow`, `synphony.workflow_store`                          |
| `config.ex`, `config/schema.ex`                | `synphony.config`                                                       |
| `linear/`*, `tracker.ex`                       | `synphony.tracker`, `synphony.tracker.jira_acli`                        |
| `workspace.ex`                                 | `synphony.workspace`                                                    |
| `orchestrator.ex`                              | `synphony.orchestrator`                                                 |
| `agent_runner.ex`                              | `synphony.agent_runner`                                                 |
| `codex/app_server.ex`, `codex/dynamic_tool.ex` | `synphony.agents.codex` (app-server client + dynamic tools)             |
| *(new)*                                        | `synphony.agents.claude` (Claude Code CLI backend)                      |
| *(new)*                                        | `synphony.agents.base` / `synphony.agent_backend` (protocol + registry) |
| `prompt_builder.ex`                            | `synphony.prompt`                                                       |
| `path_safety.ex`                               | `synphony.path_safety`                                                  |
| `http_server.ex`, `symphony_elixir_web/`*      | `synphony.http` (optional)                                              |
| `ssh.ex`                                       | defer or port later (SPEC Appendix A — optional)                        |


---

## 13. Definition of Done (first usable synphony-py)

Minimum bar before calling the migration “usable”:

- Loads and hot-reloads `WORKFLOW.md`.
- Polls Jira via `**acli`** for candidate work using configured states/project/JQL.
- Creates per-issue workspaces and runs hooks safely.
- `**AgentBackend` abstraction** in place with **two** working implementations: **Codex (app-server)** per SPEC and **Claude Code CLI** per spike — selectable via workflow config (`agent.provider` or equivalent).
- Reconciles running sessions with Jira state changes; cleans terminal workspaces on startup and transitions.
- Structured logs suitable for operators (provider id on agent-related logs recommended).

**Not required for first usable:** GitHub Copilot, Pi.dev, OpenCode, or any other third agent CLI.

---

## Open questions (resolve during spikes)

1. Which `**acli` commands** are stable for non-interactive issue listing and field reads?
2. What is the **official machine interface** for Claude Code CLI (streaming JSON vs plain text vs MCP)?
3. Should workflow use **Jira status names** only, or **status category** + name?
4. Do we expose a **Jira mutation** path for agents (`acli` vs REST) or keep mutations entirely manual?
5. **Default `agent.provider`:** if omitted, default to `codex` (SPEC continuity) or require explicit choice — team preference?

---

*Generated for the synphony-py migration; update tasks as spikes land.*