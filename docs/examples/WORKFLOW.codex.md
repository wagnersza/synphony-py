---
tracker:
  kind: jira
  jql: 'project = DEMO AND status in ("Ready")'
  active_states:
    - Ready
  terminal_states:
    - Done
    - Canceled

workspace:
  root: .synphony/workspaces

hooks:
  before_run: uv sync
  timeout_ms: 60000

agent:
  provider: codex
  max_turns: 20

codex:
  command: codex app-server
---
You are working on Jira issue {{ issue.identifier }}: {{ issue.title }}.

Use the current repository state as the source of truth. Keep changes focused on
the issue, run the relevant tests, and stop when the issue is complete or truly
blocked.
