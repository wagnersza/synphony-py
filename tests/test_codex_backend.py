from __future__ import annotations

import json
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from synphony.agents.base import AgentTurnInput
from synphony.agents.codex import CodexBackend
from synphony.errors import AgentProtocolError, AgentTimeoutError
from synphony.models import AgentEvent, Issue, Workspace


def test_codex_backend_starts_session_and_normalizes_events(
    tmp_path: Path,
    make_issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_path = tmp_path / "codex.trace"
    script_path = _write_fake_codex(tmp_path, scenario="success")
    monkeypatch.setenv("SYNPHONY_CODEX_TRACE", str(trace_path))
    observed: list[AgentEvent] = []
    workspace = _workspace(tmp_path)
    backend = CodexBackend(
        command=_python_command(script_path),
        approval_policy="never",
        thread_sandbox="read-only",
        turn_sandbox_policy={"type": "workspaceWrite", "networkAccess": False},
    )

    result = backend.start_session(
        AgentTurnInput(
            provider="codex",
            prompt="Implement DEMO-1",
            issue=make_issue,
            workspace=workspace,
            on_event=observed.append,
        )
    )

    backend.stop_session(result.session_id)
    trace = _read_trace(trace_path)
    thread_start = _message(trace, "thread/start")
    turn_start = _message(trace, "turn/start")

    assert result.session_id == "codex:thread-1:turn-1"
    assert result.turn_id == "turn-1"
    assert [event.kind for event in result.events] == [
        "session.started",
        "turn.started",
        "turn.progress",
        "turn.completed",
    ]
    assert observed == list(result.events)
    assert result.events[-1].usage is not None
    assert result.events[-1].usage.total_tokens == 8
    assert result.events[-1].rate_limits == {"primary": {"remaining": 12}}
    assert thread_start["params"]["approvalPolicy"] == "never"
    assert thread_start["params"]["sandbox"] == "read-only"
    assert turn_start["params"]["cwd"] == workspace.path
    assert turn_start["params"]["input"] == [{"type": "text", "text": "Implement DEMO-1"}]
    assert turn_start["params"]["sandboxPolicy"] == {
        "type": "workspaceWrite",
        "networkAccess": False,
    }


def test_codex_backend_continues_existing_thread(
    tmp_path: Path,
    make_issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_path = tmp_path / "codex.trace"
    script_path = _write_fake_codex(tmp_path, scenario="success")
    monkeypatch.setenv("SYNPHONY_CODEX_TRACE", str(trace_path))
    workspace = _workspace(tmp_path)
    backend = CodexBackend(command=_python_command(script_path))

    first = backend.start_session(
        AgentTurnInput(
            provider="codex",
            prompt="First turn",
            issue=make_issue,
            workspace=workspace,
        )
    )
    second = backend.continue_session(
        AgentTurnInput(
            provider="codex",
            prompt="Continuation guidance",
            issue=make_issue,
            workspace=workspace,
            session_id=first.session_id,
        )
    )

    backend.stop_session(second.session_id)
    turn_starts = [
        message for message in _read_trace(trace_path) if message.get("method") == "turn/start"
    ]

    assert second.session_id == "codex:thread-1:turn-2"
    assert [message["params"]["threadId"] for message in turn_starts] == ["thread-1", "thread-1"]
    assert turn_starts[1]["params"]["input"] == [{"type": "text", "text": "Continuation guidance"}]


def test_codex_backend_maps_failed_turn_to_protocol_error(
    tmp_path: Path,
    make_issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = _write_fake_codex(tmp_path, scenario="failed")
    monkeypatch.setenv("SYNPHONY_CODEX_TRACE", str(tmp_path / "codex.trace"))
    backend = CodexBackend(command=_python_command(script_path))

    with pytest.raises(AgentProtocolError) as exc_info:
        backend.start_session(
            AgentTurnInput(
                provider="codex",
                prompt="Fail this turn",
                issue=make_issue,
                workspace=_workspace(tmp_path),
            )
        )

    assert exc_info.value.details["provider"] == "codex"
    assert exc_info.value.details["event"] == "turn.failed"


def test_codex_backend_enforces_turn_timeout(
    tmp_path: Path,
    make_issue: Issue,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script_path = _write_fake_codex(tmp_path, scenario="hang")
    monkeypatch.setenv("SYNPHONY_CODEX_TRACE", str(tmp_path / "codex.trace"))
    backend = CodexBackend(command=_python_command(script_path), turn_timeout_ms=50)

    with pytest.raises(AgentTimeoutError) as exc_info:
        backend.start_session(
            AgentTurnInput(
                provider="codex",
                prompt="Hang this turn",
                issue=make_issue,
                workspace=_workspace(tmp_path),
            )
        )

    assert exc_info.value.details == {"provider": "codex", "timeout_ms": 50}


def _workspace(tmp_path: Path) -> Workspace:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir(exist_ok=True)
    return Workspace(path=str(workspace_path), key="demo-1", created_now=True)


def _python_command(script_path: Path) -> str:
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script_path))}"


def _write_fake_codex(tmp_path: Path, *, scenario: str) -> Path:
    script_path = tmp_path / f"fake_codex_{scenario}.py"
    script_path.write_text(
        f"""
from __future__ import annotations

import json
import os
import sys
import time

scenario = {scenario!r}
trace_path = os.environ["SYNPHONY_CODEX_TRACE"]
turn_count = 0


def emit(payload):
    print(json.dumps(payload), flush=True)


for line in sys.stdin:
    payload = json.loads(line)
    with open(trace_path, "a", encoding="utf-8") as trace:
        trace.write(json.dumps(payload) + "\\n")

    method = payload.get("method")
    request_id = payload.get("id")

    if request_id == 1:
        emit({{"id": 1, "result": {{}}}})
    elif method == "initialized":
        continue
    elif method == "thread/start":
        emit({{"id": request_id, "result": {{"thread": {{"id": "thread-1"}}}}}})
    elif method == "turn/start":
        turn_count += 1
        turn_id = f"turn-{{turn_count}}"
        emit({{"id": request_id, "result": {{"turn": {{"id": turn_id}}}}}})
        if scenario == "hang":
            time.sleep(10)
        elif scenario == "failed":
            emit({{"method": "turn/failed", "params": {{"reason": "boom"}}}})
        else:
            emit({{"method": "turn/progress", "params": {{"message": "working"}}}})
            emit({{
                "method": "turn/completed",
                "params": {{
                    "usage": {{"input_tokens": 3, "output_tokens": 5, "total_tokens": 8}},
                    "rate_limits": {{"primary": {{"remaining": 12}}}},
                }},
            }})
""".lstrip(),
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR)
    return script_path


def _read_trace(trace_path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in trace_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _message(messages: list[dict[str, Any]], method: str) -> dict[str, Any]:
    for message in messages:
        if message.get("method") == method:
            return message
    raise AssertionError(f"missing message: {method}")
