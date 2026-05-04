# synphony-py Architecture Notes

## Jira and Claude Compliance Profile

`synphony-py` follows the Symphony orchestration model while choosing Jira and
Claude Code as explicit production extensions to the upstream Linear/Codex
profile. `tracker.kind: jira` preserves the shared tracker contract: fetch
dispatch candidates, fetch issues by configured terminal states for startup
cleanup, and refresh running issue states by id for reconciliation. Jira status
names are configured directly as workflow active and terminal state names.

`agent.provider: claude` is the production agent-provider extension for this
repository. It must implement the provider-neutral `AgentBackend` contract:
start a first turn from the per-issue workspace, continue or fail continuation
turns according to the documented Claude CLI capability, emit normalized agent
events, respect configured timeouts, and surface missing executable, nonzero
exit, timeout, approval, and user-input-required outcomes as typed failures or
events. Until the Claude CLI spike is complete, production policy is conservative:
headless runs must not wait indefinitely for approvals or interactive user input;
approval or user-input-required states should fail clearly and be retried or
handled by the orchestrator policy rather than blocking a worker forever.

The long-running `synphony <WORKFLOW.md>` service is the production path. A
future `--once` mode may exist only as a local smoke-test helper that attempts at
most one issue and exits; it is not the scheduler/runner service described by
the spec.

Ticket writes are outside the orchestrator boundary. Jira transitions, comments,
and PR links should be made by the coding agent through workflow instructions or
explicit tools. Hidden scheduler business logic should not mutate Jira tickets.

Workflow front matter is optional. When it is absent, the whole file is treated
as the prompt and config defaults apply where possible. Relative
`workspace.root` values resolve from the selected workflow file's directory;
`~` and environment variables are expanded only for path fields. Hook commands
live under the top-level `hooks` block, not under `workspace.hooks`.

Runtime config defaults:

- `workspace.root`: `.synphony/workspaces`
- `tracker.active_states`: `["Ready"]`
- `tracker.terminal_states`: `["Done", "Canceled"]`
- `polling.interval_ms`: `5000`
- `agent.max_concurrent_agents`: `1`
- `agent.max_concurrent_agents_by_state`: `{}`
- `agent.max_turns`: `20`
- `agent.max_retry_backoff_ms`: `60000`
- `hooks.timeout_ms`: `60000`
- `<provider>.timeout_ms`: unset, meaning the backend default applies

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
