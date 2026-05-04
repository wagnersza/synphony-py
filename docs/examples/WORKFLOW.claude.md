---
tracker:
  kind: jira
  jql: 'project = DEMO AND status in ("Ready", "In Progress") ORDER BY priority DESC, created ASC'
  active_states:
    - Ready
    - In Progress
  terminal_states:
    - Done
    - Closed

workspace:
  root: .synphony/workspaces
  hooks:
    after_create: git status --short
    before_run: uv sync
    after_run: git status --short
    before_remove: git status --short

polling:
  interval_ms: 5000

agent:
  provider: claude
  max_turns: 6
  max_concurrent_agents: 2
  max_concurrent_agents_by_state:
    Ready: 1
    In Progress: 1

claude:
  command: claude --print
  read_timeout_ms: 30000
  turn_timeout_ms: 900000
  stall_timeout_ms: 300000
  approvals:
    mode: non_interactive
---
You are working on Jira issue {{ issue.identifier }}: {{ issue.title }}.

Use the existing repository conventions, keep changes scoped to the issue, and run the relevant verification before finishing.

Attempt: {{ attempt.number }}
