# synphony-py

`synphony-py` is the planned Python implementation of Symphony: a long-running orchestration service that polls an issue tracker, creates isolated per-issue workspaces, and runs coding-agent sessions to move work forward.

This repository is currently in the migration/bootstrap stage. The implementation plan is tracked in [`PLAN.md`](PLAN.md), with the source backlog in [`tasks.md`](tasks.md). The target behavior follows the language-agnostic Symphony specification at [`../symphony/SPEC.md`](../symphony/SPEC.md) and uses the Elixir implementation under [`../symphony/elixir`](../symphony/elixir) as the reference port.

## Scope

The first usable milestone keeps the core Symphony model but adapts two product choices:

- **Issue tracker:** Jira through the Atlassian CLI, `acli`.
- **Coding agents:** pluggable agent backend interface with v1 support for `codex` and `claude` only.

Future providers such as GitHub Copilot CLI, Pi.dev, and OpenCode should be reserved in the design but not implemented in the first pass.

## Prerequisites

Runtime prerequisites depend on the selected workflow provider:

- Python 3.11+.
- `uv` for dependency management and local command execution.
- `acli` must be installed, on `PATH`, and already authenticated for Jira access.
- `codex` must be installed and on `PATH` when using the Codex backend.
- Claude Code CLI must be installed and on `PATH` when using the Claude backend.
- Workspace hooks will run through the configured shell, expected to be `sh -lc` or `bash -lc` depending on the final workflow config.

## Quick Start

Install dependencies and run the current verification suite:

```bash
uv sync

uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

The `synphony` console script is reserved but not wired to the orchestrator yet. CLI execution is planned for Phase 6 in [`PLAN.md`](PLAN.md).

## Workflow Configuration

`synphony-py` will load a repository-owned `WORKFLOW.md` with YAML front matter plus a prompt body. The workflow selects the tracker and agent provider.

Minimal shape for Codex:

```yaml
---
tracker:
  kind: jira
  jql: 'project = ABC AND status = "Ready"'

agent:
  provider: codex

codex:
  command: codex app-server
  approval_policy: never
  thread_sandbox: read-only
  turn_sandbox_policy:
    type: workspaceWrite
    networkAccess: false
  read_timeout_ms: 30000
  turn_timeout_ms: 3600000
---
```

Minimal shape for Claude:

```yaml
---
tracker:
  kind: jira
  jql: 'project = ABC AND status = "Ready"'

agent:
  provider: claude

claude:
  command: claude
---
```

Exact Jira fields, Claude CLI options, and provider-specific timeout keys are still subject to the `acli` and Claude CLI spikes in [`PLAN.md`](PLAN.md).

## Architecture

The planned package layout is:

```text
src/synphony/
  workflow.py          # WORKFLOW.md loading and prompt rendering
  config.py            # typed config access and validation
  tracker/             # tracker protocol, memory tracker, Jira acli adapter
  workspace.py         # workspace creation, reuse, hooks, cleanup
  agents/              # AgentBackend protocol, registry, Codex, Claude
  agent_runner.py      # provider-agnostic run loop
  orchestrator.py      # polling, dispatch, retries, reconciliation
  cli.py               # synphony command entrypoint
```

The orchestrator should depend on stable internal protocols rather than concrete providers:

- `Tracker` handles Jira or test memory issues.
- `AgentBackend` handles Codex or Claude execution.
- `Workspace` enforces path safety and lifecycle hooks.

## Development Plan

Work should follow [`PLAN.md`](PLAN.md):

1. Reconcile the SPEC with Jira and multi-backend support.
2. Bootstrap the Python project and tooling.
3. Implement models, workflow loading, tracker/workspace foundations, and fake test backends.
4. Prove orchestrator behavior with memory/fake implementations before real CLIs.
5. Add Jira `acli`, Codex app-server, and Claude Code CLI integrations.
6. Add CLI, logging, examples, CI, and final release checks.

## Agent Guidance

Project-specific agent instructions live in [`AGENTS.md`](AGENTS.md). The copied
upstream agent skills are mirrored for the supported coding agents:

- Claude Code: [`.claude/skills/`](.claude/skills/) plus [`CLAUDE.md`](CLAUDE.md).
- Cursor: [`.cursor/skills/`](.cursor/skills/) plus selected always-loaded rules in [`.cursor/rules/`](.cursor/rules/).
- GitHub Copilot: [`.github/skills/`](.github/skills/) plus [`.github/copilot-instructions.md`](.github/copilot-instructions.md).

