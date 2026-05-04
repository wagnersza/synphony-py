# synphony-py Architecture Notes

## Spec Compliance Profile

The upstream Symphony specification is centered on Linear as the issue tracker
and Codex as the agent provider. This repository intentionally extends those
two integration points while preserving the remainder of the spec's abstract
model: polling loop, per-issue workspaces, provider-neutral `AgentBackend`,
lifecycle hooks, retry/backoff, and stall detection.

This section is the authoritative record of each extension decision. Code that
departs from the upstream spec must be justified here rather than silently
diverging.

### Jira as the Tracker Extension

`tracker.kind: jira` is the production tracker extension, replacing the
upstream's Linear tracker. The adapter preserves all three operations of the
`Tracker` protocol:

- `fetch_candidate_issues()` — issues eligible for dispatch, filtered by
  configured `active_states` and a workflow-provided JQL base query.
- `fetch_issues_by_states(state_names)` — used at startup to locate terminal
  workspaces for best-effort cleanup.
- `fetch_issue_states_by_ids(issue_ids)` — used during reconciliation to
  refresh the state of running issues without re-fetching the full candidate
  list.

Jira status names map directly to the workflow's `active_states` and
`terminal_states` lists. Comparison is case-insensitive. There is no automatic
status-name translation; operators must use the exact Jira status strings in
their workflow configuration.

Jira labels are normalized to lowercase. Blocker links are extracted from the
`issuelinks` field: any inward link whose `inward` label contains
`"blocked by"` is treated as a blocker reference.

### Claude Code as the Agent Extension

`agent.provider: claude` is the production agent-provider extension, replacing
the upstream's Codex provider. `ClaudeBackend` implements the shared
`AgentBackend` protocol. The full CLI contract is documented in the
[Claude Code CLI Contract](#claude-code-cli-contract) section below.

Known limitations relative to the upstream spec:

- **Codex app-server sessions:** The Codex app-server protocol is not supported.
  The Claude backend uses one-shot `claude -p` invocations and `--resume` for
  continuation turns.
- **Provider-native user-input-required events:** Claude Code does not expose a
  separate stable `user_input_required` JSON event. The backend infers this
  condition from non-empty `permission_denials` and the final assistant message.
- **Wall-clock timeout control:** The Claude CLI has no general
  `--max-wall-clock-time` flag. Synphony enforces provider timeouts by
  terminating the subprocess and records a `timeout` event distinct from
  Claude's own `terminal_reason: "max_turns"`.
- **Usage/rate-limit guarantees:** Token usage and cost fields are extracted
  when present in the JSON result but may be absent. Null usage is accepted.

### Production Service Mode vs. `--once`

The production CLI entry point (`synphony <WORKFLOW.md>`) starts the long-running
poll/reconcile/dispatch loop described in the spec. This is the only supported
production mode.

`synphony --once <WORKFLOW.md>`, if implemented, is a **smoke-test helper only**.
It attempts at most one eligible issue and exits, which is useful for local
validation but provides no retry, reload, stall detection, or graceful shutdown
guarantees. Do not use `--once` as a substitute for the daemon in production.

### Tracker-Write Boundary

The orchestrator does not write to Jira. Issue state transitions, comments, PR
links, and any other Jira mutations are the responsibility of the agent via
workflow instructions or explicitly granted tools. The orchestrator reads issue
state for dispatch eligibility and reconciliation; it never performs a write on
behalf of the agent.

This boundary exists for two reasons:

1. The orchestrator does not know whether the agent's work actually warrants a
   status transition. Only the agent has the context to make that judgment.
2. Hidden orchestrator writes would create a split ownership problem: operators
   and auditors would need to look in two places to understand what changed a
   Jira ticket.

### Claude Approval and User-Input Policy

Production runs must not block on interactive approval prompts. The backend
uses `--permission-mode dontAsk` and an explicit `--allowedTools` allowlist so
that missing permissions produce deterministic denials rather than blocking
prompts.

`--dangerously-skip-permissions` and `--permission-mode bypassPermissions` are
not permitted in the default production profile. Operators who intentionally
want broader tool access must set this explicitly in their workflow config, and
the choice should be reviewed as a security-relevant configuration decision.

Any run that cannot proceed due to permission denials is recorded as a
`user_input_required` or `approval_required` attempt outcome, not as a generic
failure, so retry policy can treat the two cases differently.

### Unknown Workflow Keys

Unknown top-level workflow configuration keys are silently ignored to preserve
forward compatibility. Operators should not rely on this behavior for
intentional polymorphism; use versioned workflow keys when adding new fields.

---

## Phase 2: Tracker and Workspace Foundation

The orchestrator talks to trackers through `synphony.tracker.base.Tracker`.
The protocol has three operations:

- `fetch_candidate_issues()` for active issues eligible for dispatch.
- `fetch_issues_by_states(state_names)` for startup terminal cleanup.
- `fetch_issue_states_by_ids(issue_ids)` for reconciliation of running issues.

`MemoryTracker` is the deterministic unit-test implementation. It stores real
`Issue` models, filters states case-insensitively, preserves blockers and
priority fields, and sorts candidates by priority, creation time, then
identifier so orchestrator tests can exercise dispatch cases without Jira.

`JiraAcliTracker` invokes the Atlassian CLI with a short timeout and expects
JSON output. Unit tests use sanitized fixtures under `tests/fixtures/acli/`; no
unit test requires a real Jira site or authenticated `acli`.

Local `acli --help` discovery on 2026-05-04 showed that Jira issue operations
are currently exposed as `jira workitem`, not `jira issue`. The adapter uses:

```bash
acli jira workitem search --jql '<base JQL> AND status in ("Ready")' \
  --fields key,summary,status,description,priority,labels,issuelinks,created,updated \
  --limit 50 \
  --json

acli jira workitem view KEY-123 \
  --fields key,summary,status,description,priority,labels,issuelinks,created,updated \
  --json
```

The adapter maps Jira status names directly into `Issue.state`; workflow active
and terminal states should therefore be Jira status names compared with
case-insensitive normalization. Jira blocker support is represented from either
an explicit `blocked_by` JSON field or inward issue links whose inward label
contains `blocked by`.

Open items for the real Jira integration pass:

- Capture authenticated output for pagination with `--paginate` versus bounded
  `--limit 50`.
- Confirm whether `created`, `updated`, `labels`, and `issuelinks` are returned
  by `workitem search --json --fields ...` for the target Jira site.
- Confirm whether blocker links use `is blocked by` consistently across the
  target workflow, or whether custom link names need workflow configuration.

## Claude Code CLI Contract

Claude Code is the production agent-provider extension for this repository.
Local discovery on 2026-05-04 used Claude Code CLI `2.1.126` and the official
Claude Code CLI/headless documentation:

- `https://docs.claude.com/en/docs/claude-code/headless`
- `https://code.claude.com/docs/en/cli-reference`
- `https://code.claude.com/docs/en/permission-modes`
- `https://code.claude.com/docs/en/agent-sdk/structured-outputs`

The machine-safe non-interactive command form is `claude -p` with explicit
output, permission, and stdin handling:

```bash
claude --bare -p "$PROMPT" \
  --output-format json \
  --permission-mode dontAsk \
  --allowedTools "Read,Edit,Bash(uv run pytest *)" \
  --max-turns "$CLAUDE_AGENTIC_MAX_TURNS" \
  < /dev/null
```

Set or omit Claude's `--max-turns` independently from Synphony's outer
`agent.max_turns`; it limits tool/assistant turns inside one CLI invocation.

For deterministic scripted runs, `--bare` avoids ambient hooks, plugins, MCP
servers, memory, and `CLAUDE.md` auto-discovery. The backend may omit `--bare`
only when workflow policy intentionally wants project/user Claude Code context;
that choice must be visible in configuration because stream output can otherwise
contain local paths, plugin names, and MCP server state.

### IO, Exit, and Structured Output

- Prompt text can be passed as the positional prompt and extra input can be
  piped on stdin. If no stdin is intended, pass `< /dev/null`; otherwise the CLI
  waits briefly and emits a `no stdin data received` warning before continuing.
- `stdout` carries the agent response. With `--output-format text`, this is plain
  text. With `--output-format json`, it is a single JSON result object. With
  `--output-format stream-json --verbose`, it is newline-delimited JSON events
  ending in a result object.
- `stderr` carries CLI warnings and argument/auth/runtime diagnostics. Invalid
  arguments can exit before any JSON is emitted, so the backend must preserve
  safe stderr snippets for operator errors.
- Observed exit codes: successful text/JSON runs exit `0`; invalid CLI arguments
  exit `1` without structured JSON; `terminal_reason: "max_turns"` exits `1`
  with a JSON result; denied tools in `dontAsk` mode can still exit `0` if Claude
  handles the denial and returns a final message.
- The backend must parse both process exit status and JSON fields such as
  `is_error`, `subtype`, `terminal_reason`, `stop_reason`, and
  `permission_denials`. Exit code alone is not enough.
- `--output-format json` exposes `session_id`, timing fields, `num_turns`,
  `result`, `total_cost_usd`, usage/model usage, permission denials, and a
  `structured_output` field when `--json-schema` is supplied and validation
  succeeds. Sanitized examples live under `tests/fixtures/claude/`.

### Sessions and Continuation

Continuation turns are supported by the Claude Code CLI contract. The documented
forms are `claude -p "next prompt" --continue` for the most recent conversation
in the current directory and `claude -p "next prompt" --resume "$SESSION_ID"` for
a specific captured session. Synphony should prefer `--resume "$SESSION_ID"` so
the orchestrator owns the session identifier recorded from the previous JSON
result.

Continuation requires Claude Code session persistence. Do not use
`--no-session-persistence` for sessions that Synphony may continue. A local
sandboxed resume smoke returned `No conversation found with session ID: ...`,
which means the backend must treat resume lookup failure as a typed provider
failure instead of silently starting a new task or pretending continuation
succeeded.

### Approval, User Input, and Timeouts

Production runs must not rely on interactive approval prompts. Use
`--permission-mode dontAsk` plus an explicit `--allowedTools` allowlist (or a
reviewed settings file) so missing permissions become denials, not blocking
prompts. Do not use `--dangerously-skip-permissions` or
`--permission-mode bypassPermissions` for the default production profile.

In local smoke testing, a denied Bash call returned a successful JSON result with
a populated `permission_denials` array and an explanatory message. The backend
should convert any non-empty `permission_denials` into a provider event and, when
the requested work cannot proceed, a user-input-required or approval-required
failure. Claude Code does not expose a separate stable
`user_input_required` JSON event in the observed result schema.

Claude Code exposes `--max-turns` and `--max-budget-usd`, but no general
wall-clock timeout flag was found for `claude -p`. Synphony should enforce
provider timeouts around the subprocess, terminate the process on timeout, and
classify the attempt separately from Claude's own `terminal_reason: "max_turns"`.

Unsupported or limited spec concepts for the Claude profile:

- Codex-specific app-server protocol messages and long-lived app-server sessions.
- Interactive approval prompts during production background runs.
- A stable provider-native `user_input_required` event separate from permission
  denials or final assistant text.
- Provider-native wall-clock timeout control for a `claude -p` invocation.
- Guaranteed usage/rate-limit fields beyond the observed usage and cost metadata.
- Session continuation when Claude Code session persistence is disabled or
  unavailable.

Workspace management lives in `synphony.workspace`. Workspaces are deterministic
`<workspace.root>/<workspace_key>` paths derived from issue identifiers, and the
path safety layer rejects parent traversal and verifies every computed path
remains under the configured root. Lifecycle hooks run with the workspace as
`cwd`, through a configurable shell tuple, and with a timeout. Removal runs the
`before_remove` hook before deleting the workspace best-effort.
