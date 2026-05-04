# synphony-py Architecture Notes

## Claude Code CLI Contract

Phase 5 uses the documented Claude Code programmatic CLI path:

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

`ClaudeBackend` treats each turn as a one-shot subprocess. It appends the required non-interactive stream-json flags to the configured `claude.command`, runs with `cwd` set to the issue workspace, reads stdout as JSON lines, drains stderr separately, and maps raw events into provider-agnostic `AgentEvent` values.

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

Both paths kill the subprocess and raise `AgentTimeoutError`, so a permission prompt, hung CLI, or silent stalled run cannot block the orchestrator forever.

Continuation uses `claude --resume <session_id>` when `run_continuation_turn` receives a previous session id. Claude Code session persistence is a CLI-level behavior; if a local install cannot resume non-interactive sessions, the backend surfaces the nonzero CLI exit as `AgentProtocolError`.

Custom dynamic tools are not implemented for Claude in this phase. Jira-side dynamic tools remain a Codex-specific follow-up unless Claude Code exposes a stable non-interactive custom-tool contract that matches Symphony's needs.
