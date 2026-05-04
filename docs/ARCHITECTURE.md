# synphony-py Architecture Notes

## Phase 2: Tracker and Workspace Foundation

The orchestrator talks to trackers through `synphony.tracker.base.Tracker`.
The protocol has three operations:

- `fetch_candidate_issues()` for active issues eligible for dispatch.
- `fetch_issues_by_states(state_names)` for startup terminal cleanup.
- `fetch_issue_states_by_ids(issue_ids)` for reconciliation of running issues.

`MemoryTracker` is the deterministic unit-test implementation. It stores real
`Issue` models, filters states case-insensitively when active states are
configured, preserves blockers and priority fields, and sorts candidates by
priority, creation time, then identifier so orchestrator tests can exercise
dispatch cases without Jira.

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

Workspace management lives in `synphony.workspace`. Workspaces are deterministic
`<workspace.root>/<workspace_key>` paths derived from issue identifiers, and the
path safety layer rejects parent traversal and verifies every computed path
remains under the configured root. Lifecycle hooks run with the workspace as
`cwd`, through a configurable shell tuple, and with a timeout. Removal runs the
`before_remove` hook before deleting the workspace best-effort.

## Phase 5: Codex App-Server Backend

`synphony.agents.codex.CodexBackend` launches `bash -lc <codex.command>` with
`cwd` set to the issue workspace, keeps stdout as the JSON-line protocol stream,
and drains stderr separately so non-protocol output cannot corrupt protocol
parsing.

Startup follows the Codex app-server sequence used by the Elixir reference:

1. Send `initialize`, then `initialized`.
2. Send `thread/start` with the workspace `cwd` plus configured approval and
   thread sandbox values.
3. Send `turn/start` with the prompt, issue title, workspace `cwd`, and optional
   turn sandbox policy.

The backend normalizes app-server updates into `AgentEvent` values with provider
`codex`, `session_id` built from the Codex thread and turn ids, optional usage,
and optional rate-limit data. Successful turns leave the app-server process alive
for continuation on the same thread; `stop_session()` terminates it.

Policy for non-interactive operation is conservative:

- Approval requests are auto-approved only when `codex.approval_policy` is
  `never`, matching the high-trust non-interactive behavior from the reference.
- Operator input requests fail the turn immediately with `AgentProtocolError`.
- Unsupported client-side tool calls receive a structured failure response so
  the Codex turn can keep streaming instead of hanging.

## Phase 5: Claude Code CLI Backend

The Claude backend uses the documented non-interactive CLI path:

```bash
claude --bare --print --output-format stream-json --verbose --include-partial-messages "<prompt>"
```

The local `claude --help` output confirms the same core flags:

- `--print` / `-p` runs non-interactively and exits.
- `--output-format stream-json` emits newline-delimited JSON events.
- `--include-partial-messages` includes token-like partial message chunks.
- `--resume <session_id>` continues a previous session when Claude Code has persisted it.
- `--permission-mode` and `--allowedTools` are the non-interactive approval controls.
- `--bare` skips local hook/plugin/skill auto-discovery for faster, more deterministic scripted calls.

`ClaudeBackend` treats each turn as a one-shot subprocess. It appends the
required non-interactive stream-json flags to the configured `claude.command`,
runs with `cwd` set to the issue workspace, reads stdout as JSON lines, drains
stderr separately, and maps raw events into provider-agnostic `AgentEvent`
values.

Normalized event mapping:

- `system/init` -> `session.started`
- `stream_event` text deltas -> `message.delta`
- `assistant` messages -> `message`
- `result` success -> `turn.completed`
- `result` error/failure -> `turn.failed`
- other typed/subtyped events preserve their `type.subtype` shape

Timeouts are enforced by the backend while reading stdout:

- `turn_timeout_ms` caps the total subprocess runtime.
- `stall_timeout_ms` caps time without any stdout event.

Both paths kill the subprocess and raise `AgentTimeoutError`, so a permission
prompt, hung CLI, or silent stalled run cannot block the orchestrator forever.

Continuation uses `claude --resume <session_id>` when a previous session id is
available. Claude Code session persistence is a CLI-level behavior; if a local
install cannot resume non-interactive sessions, the backend surfaces the nonzero
CLI exit as `AgentProtocolError`.

Custom dynamic tools are not implemented for Claude in this phase. Jira-side
dynamic tools remain a Codex-specific follow-up unless Claude Code exposes a
stable non-interactive custom-tool contract that matches Symphony's needs.
