# synphony-py Architecture Notes

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

Workspace management lives in `synphony.workspace`. Workspaces are deterministic
`<workspace.root>/<workspace_key>` paths derived from issue identifiers, and the
path safety layer rejects parent traversal and verifies every computed path
remains under the configured root. Lifecycle hooks run with the workspace as
`cwd`, through a configurable shell tuple, and with a timeout. Removal runs the
`before_remove` hook before deleting the workspace best-effort.

## Phase 5: Codex App-Server Backend

`synphony.agents.codex.CodexBackend` is the first real `AgentBackend`
implementation. It launches `bash -lc <codex.command>` with `cwd` set to the
issue workspace, keeps stdout as the JSON-line protocol stream, and drains
stderr separately so non-protocol output cannot corrupt protocol parsing.

Startup follows the Codex app-server sequence used by the Elixir reference:

1. Send `initialize`, then `initialized`.
2. Send `thread/start` with the workspace `cwd` plus configured approval and
   thread sandbox values.
3. Send `turn/start` with the prompt, issue title, workspace `cwd`, and optional
   turn sandbox policy.

The backend normalizes app-server updates into `AgentEvent` values with provider
`codex`, `session_id` built from the Codex thread and turn ids, optional usage,
and optional rate-limit data. Successful turns leave the app-server process alive
for `continue_session()` on the same thread; `stop_session()` terminates it.

Policy for non-interactive operation is conservative:

- Approval requests are auto-approved only when `codex.approval_policy` is
  `never`, matching the high-trust non-interactive behavior from the reference.
- Operator input requests fail the turn immediately with `AgentProtocolError`.
- Unsupported client-side tool calls receive a structured failure response so
  the Codex turn can keep streaming instead of hanging.
