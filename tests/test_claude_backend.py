from __future__ import annotations

import shlex
import sys
from pathlib import Path

import pytest

from synphony.agents.base import AgentTurnRequest
from synphony.agents.claude import ClaudeBackend, ClaudeBackendConfig
from synphony.errors import AgentProtocolError, AgentTimeoutError
from synphony.models import AgentEvent


def _python_command(source: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(source)}"


def test_claude_backend_runs_print_mode_and_normalizes_stream_events(tmp_path: Path) -> None:
    source = r"""
import json
import os
import sys

assert "--print" in sys.argv
assert "--output-format" in sys.argv
assert "stream-json" in sys.argv
assert "--verbose" in sys.argv
assert "--include-partial-messages" in sys.argv
assert sys.argv[-1] == "build it"

events = [
    {"type": "system", "subtype": "init", "session_id": "sess-1", "cwd": os.getcwd()},
    {
        "type": "stream_event",
        "session_id": "sess-1",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "hello"},
        },
    },
    {
        "type": "assistant",
        "session_id": "sess-1",
        "message": {
            "id": "msg-1",
            "content": [{"type": "text", "text": "done"}],
            "usage": {"input_tokens": 2, "output_tokens": 3},
        },
    },
    {"type": "result", "subtype": "success", "session_id": "sess-1", "result": "done"},
]
for event in events:
    print(json.dumps(event), flush=True)
"""
    backend = ClaudeBackend(
        ClaudeBackendConfig(command=_python_command(source), turn_timeout_ms=2000)
    )
    events: list[AgentEvent] = []

    result = backend.run_first_turn(
        AgentTurnRequest(prompt="build it", cwd=tmp_path),
        on_event=events.append,
    )

    assert result.session_id == "sess-1"
    assert result.message == "done"
    assert [event.kind for event in events] == [
        "session.started",
        "message.delta",
        "message",
        "turn.completed",
    ]
    assert events[0].raw["cwd"] == str(tmp_path)
    assert events[1].message == "hello"
    assert events[2].usage is not None
    assert events[2].usage.input_tokens == 2
    assert events[2].usage.output_tokens == 3


def test_claude_backend_resumes_existing_session(tmp_path: Path) -> None:
    source = r"""
import json
import sys

resume_index = sys.argv.index("--resume")
assert sys.argv[resume_index + 1] == "sess-1"
assert sys.argv[-1] == "continue work"

print(json.dumps({"type": "system", "subtype": "init", "session_id": "sess-1"}), flush=True)
print(json.dumps({
    "type": "result",
    "subtype": "success",
    "session_id": "sess-1",
    "result": "continued",
}), flush=True)
"""
    backend = ClaudeBackend(
        ClaudeBackendConfig(command=_python_command(source), turn_timeout_ms=2000)
    )

    result = backend.run_continuation_turn(
        AgentTurnRequest(prompt="continue work", cwd=tmp_path, session_id="sess-1")
    )

    assert result.session_id == "sess-1"
    assert result.message == "continued"


def test_claude_backend_raises_protocol_error_for_bad_json(tmp_path: Path) -> None:
    backend = ClaudeBackend(
        ClaudeBackendConfig(command=_python_command("print('not-json', flush=True)"))
    )

    with pytest.raises(AgentProtocolError, match="invalid Claude stream-json"):
        backend.run_first_turn(AgentTurnRequest(prompt="work", cwd=tmp_path))


def test_claude_backend_includes_stderr_when_process_fails(tmp_path: Path) -> None:
    source = "import sys; print('permission prompt blocked', file=sys.stderr); sys.exit(7)"
    backend = ClaudeBackend(
        ClaudeBackendConfig(command=_python_command(source), turn_timeout_ms=2000)
    )

    with pytest.raises(AgentProtocolError) as exc_info:
        backend.run_first_turn(AgentTurnRequest(prompt="work", cwd=tmp_path))

    assert exc_info.value.details["exit_code"] == 7
    assert "permission prompt blocked" in exc_info.value.details["stderr"]


def test_claude_backend_enforces_stall_timeout(tmp_path: Path) -> None:
    backend = ClaudeBackend(
        ClaudeBackendConfig(
            command=_python_command("import time; time.sleep(5)"),
            stall_timeout_ms=100,
            turn_timeout_ms=2000,
        )
    )

    with pytest.raises(AgentTimeoutError):
        backend.run_first_turn(AgentTurnRequest(prompt="work", cwd=tmp_path))
