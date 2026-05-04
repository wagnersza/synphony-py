"""Claude Code CLI backend."""

from __future__ import annotations

import json
import selectors
import shlex
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from synphony.agents.base import (
    AgentEventCallback,
    AgentTurnInput,
    AgentTurnRequest,
    AgentTurnResult,
)
from synphony.errors import AgentProtocolError, AgentTimeoutError
from synphony.models import AgentEvent, AgentUsage, RunAttempt, build_session_id

_DEFAULT_TURN_TIMEOUT_MS = 30 * 60 * 1000
_DEFAULT_STALL_TIMEOUT_MS = 2 * 60 * 1000
_SELECT_INTERVAL_SECONDS = 0.1


@dataclass(frozen=True, slots=True)
class ClaudeBackendConfig:
    command: str = "claude"
    turn_timeout_ms: int = _DEFAULT_TURN_TIMEOUT_MS
    stall_timeout_ms: int = _DEFAULT_STALL_TIMEOUT_MS
    bare: bool = True
    verbose: bool = True
    include_partial_messages: bool = True
    permission_mode: str | None = None
    allowed_tools: tuple[str, ...] = ()
    max_turns: int | None = None
    extra_args: tuple[str, ...] = ()


class ClaudeBackend:
    provider = "claude"

    def __init__(self, config: ClaudeBackendConfig) -> None:
        self._config = config
        self._active_processes: dict[str, subprocess.Popen[str]] = {}

    def run_first_turn(
        self,
        request: AgentTurnRequest,
        on_event: AgentEventCallback | None = None,
    ) -> AgentTurnResult:
        return self._run_cli_turn(
            request=request,
            resume_session_id=None,
            on_event=on_event or request.on_event,
        )

    def run_continuation_turn(
        self,
        request: AgentTurnRequest,
        on_event: AgentEventCallback | None = None,
    ) -> AgentTurnResult:
        if request.session_id is None:
            raise AgentProtocolError("Claude continuation turn requires a session_id")
        return self._run_cli_turn(
            request=request,
            resume_session_id=request.session_id,
            on_event=on_event or request.on_event,
        )

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        return self.run_turn(_request_from_input(turn, turn_number=1, max_turns=1))

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        if turn.session_id is None:
            raise AgentProtocolError("Claude continuation turn requires a session_id")
        return self.run_turn(_request_from_input(turn, turn_number=1, max_turns=1))

    def run_turn(self, request: AgentTurnRequest) -> AgentTurnResult:
        if request.session_id is None:
            return self.run_first_turn(request)
        return self.run_continuation_turn(request)

    def stop(self, session_id: str) -> bool:
        process = self._active_processes.pop(session_id, None)
        if process is None or process.poll() is not None:
            return False
        process.terminate()
        return True

    def stop_session(
        self,
        session_id: str,
        *,
        cwd: Path | None = None,
        timeout: object = None,
    ) -> None:
        self.stop(session_id)

    def _run_cli_turn(
        self,
        *,
        request: AgentTurnRequest,
        resume_session_id: str | None,
        on_event: AgentEventCallback | None,
    ) -> AgentTurnResult:
        args = self._build_args(prompt=request.prompt, resume_session_id=resume_session_id)
        process = subprocess.Popen(
            args,
            cwd=str(request.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        process_key = resume_session_id or f"pending:{id(process)}"
        self._active_processes[process_key] = process

        stderr_lines: list[str] = []
        stderr_thread = threading.Thread(
            target=_drain_stderr,
            args=(process, stderr_lines),
            daemon=True,
        )
        stderr_thread.start()

        session_id = resume_session_id
        message: str | None = None
        raw_events: list[dict[str, object]] = []

        try:
            for raw_event in self._iter_stdout_events(
                process=process,
                request=request,
                turn_timeout_ms=request.turn_timeout_ms or self._config.turn_timeout_ms,
                stall_timeout_ms=request.stall_timeout_ms or self._config.stall_timeout_ms,
            ):
                raw_events.append(raw_event)
                session_id = _event_session_id(raw_event) or session_id
                event = _normalize_event(raw_event, fallback_session_id=session_id)
                if event is not None and on_event is not None:
                    on_event(event)
                message = _event_result_message(raw_event) or message
        except Exception:
            _terminate_process(process)
            raise
        finally:
            stderr_thread.join(timeout=1)
            self._active_processes.pop(process_key, None)
            if session_id is not None:
                self._active_processes.pop(session_id, None)

        exit_code = process.wait()
        if exit_code != 0:
            raise AgentProtocolError(
                f"Claude CLI exited with status {exit_code}",
                details={
                    "provider": self.provider,
                    "exit_code": exit_code,
                    "stderr": "".join(stderr_lines),
                },
            )

        if session_id is None:
            session_id = build_session_id(provider=self.provider, thread_id=None, turn_id=None)

        return AgentTurnResult(
            session_id=session_id,
            exit_code=exit_code,
            message=message,
            raw_events=tuple(raw_events),
        )

    def _build_args(self, *, prompt: str, resume_session_id: str | None) -> list[str]:
        args = [*shlex.split(self._config.command)]

        if self._config.bare and "--bare" not in args:
            args.append("--bare")
        if "--print" not in args and "-p" not in args:
            args.append("--print")
        if "--output-format" not in args:
            args.extend(["--output-format", "stream-json"])
        if self._config.verbose and "--verbose" not in args:
            args.append("--verbose")
        if self._config.include_partial_messages and "--include-partial-messages" not in args:
            args.append("--include-partial-messages")
        if self._config.permission_mode is not None and "--permission-mode" not in args:
            args.extend(["--permission-mode", self._config.permission_mode])
        for tool in self._config.allowed_tools:
            args.extend(["--allowedTools", tool])
        if self._config.max_turns is not None and "--max-turns" not in args:
            args.extend(["--max-turns", str(self._config.max_turns)])
        if resume_session_id is not None and "--resume" not in args and "-r" not in args:
            args.extend(["--resume", resume_session_id])
        args.extend(self._config.extra_args)
        args.append(prompt)
        return args

    def _iter_stdout_events(
        self,
        *,
        process: subprocess.Popen[str],
        request: AgentTurnRequest,
        turn_timeout_ms: int,
        stall_timeout_ms: int,
    ) -> Iterator[dict[str, object]]:
        if process.stdout is None:
            raise AgentProtocolError("Claude CLI stdout pipe was not available")

        started_at = time.monotonic()
        last_event_at = started_at
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)

        try:
            while process.poll() is None:
                now = time.monotonic()
                _raise_if_timed_out(
                    provider=self.provider,
                    started_at=started_at,
                    last_event_at=last_event_at,
                    now=now,
                    turn_timeout_ms=turn_timeout_ms,
                    stall_timeout_ms=stall_timeout_ms,
                    process=process,
                )

                for _key, _ in selector.select(timeout=_SELECT_INTERVAL_SECONDS):
                    line = process.stdout.readline()
                    if not line:
                        continue
                    last_event_at = time.monotonic()
                    yield _parse_event(line)

            for line in process.stdout:
                if line:
                    yield _parse_event(line)
        finally:
            selector.close()


def _request_from_input(
    turn: AgentTurnInput,
    *,
    turn_number: int,
    max_turns: int,
) -> AgentTurnRequest:
    return AgentTurnRequest(
        provider=turn.provider,
        cwd=Path(turn.workspace.path),
        issue=turn.issue,
        workspace=turn.workspace,
        attempt=RunAttempt(
            issue_id=turn.issue.id,
            issue_identifier=turn.issue.identifier,
            attempt=1,
        ),
        prompt=turn.prompt,
        turn_number=turn_number,
        max_turns=max_turns,
        session_id=turn.session_id,
        on_event=turn.on_event or _ignore_event,
    )


def _ignore_event(event: AgentEvent) -> None:
    return None


def _drain_stderr(process: subprocess.Popen[str], stderr_lines: list[str]) -> None:
    if process.stderr is None:
        return
    for line in process.stderr:
        stderr_lines.append(line)


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.kill()
    process.wait(timeout=1)


def _raise_if_timed_out(
    *,
    provider: str,
    started_at: float,
    last_event_at: float,
    now: float,
    turn_timeout_ms: int,
    stall_timeout_ms: int,
    process: subprocess.Popen[str],
) -> None:
    if (now - started_at) * 1000 > turn_timeout_ms:
        _terminate_process(process)
        raise AgentTimeoutError(provider=provider, timeout_ms=turn_timeout_ms)
    if (now - last_event_at) * 1000 > stall_timeout_ms:
        _terminate_process(process)
        raise AgentTimeoutError(provider=provider, timeout_ms=stall_timeout_ms)


def _parse_event(line: str) -> dict[str, object]:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError as exc:
        raise AgentProtocolError(
            "invalid Claude stream-json event",
            details={"line": line.strip()},
        ) from exc
    if not isinstance(parsed, dict):
        raise AgentProtocolError(
            "invalid Claude stream-json event",
            details={"line": line.strip()},
        )
    return parsed


def _normalize_event(
    raw_event: dict[str, object],
    *,
    fallback_session_id: str | None,
) -> AgentEvent | None:
    event_type = _str_value(raw_event.get("type")) or "unknown"
    subtype = _str_value(raw_event.get("subtype"))
    session_id = _event_session_id(raw_event) or fallback_session_id
    if session_id is None:
        session_id = build_session_id(provider="claude", thread_id=None, turn_id=None)

    kind = _event_kind(event_type=event_type, subtype=subtype, raw_event=raw_event)
    return AgentEvent(
        provider="claude",
        session_id=session_id,
        kind=kind,
        occurred_at=datetime.now(UTC),
        turn_id=_event_turn_id(raw_event),
        message=_event_message(raw_event),
        usage=_event_usage(raw_event),
        raw=raw_event,
    )


def _event_kind(
    *,
    event_type: str,
    subtype: str | None,
    raw_event: dict[str, object],
) -> str:
    if event_type == "system" and subtype == "init":
        return "session.started"
    if event_type == "stream_event":
        return "message.delta"
    if event_type == "assistant":
        return "message"
    if event_type == "result":
        if raw_event.get("is_error") is True or subtype in {"error", "failure"}:
            return "turn.failed"
        return "turn.completed"
    if subtype is not None:
        return f"{event_type}.{subtype}"
    return event_type


def _event_session_id(raw_event: dict[str, object]) -> str | None:
    return _str_value(raw_event.get("session_id"))


def _event_turn_id(raw_event: dict[str, object]) -> str | None:
    message = raw_event.get("message")
    if isinstance(message, dict):
        return _str_value(message.get("id"))
    return _str_value(raw_event.get("uuid"))


def _event_result_message(raw_event: dict[str, object]) -> str | None:
    if raw_event.get("type") == "result":
        return _str_value(raw_event.get("result"))
    return None


def _event_message(raw_event: dict[str, object]) -> str | None:
    if raw_event.get("type") == "stream_event":
        event = raw_event.get("event")
        if isinstance(event, dict):
            delta = event.get("delta")
            if isinstance(delta, dict):
                return _str_value(delta.get("text"))

    message = raw_event.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            return (
                "".join(
                    item.get("text", "")
                    for item in content
                    if isinstance(item, dict) and item.get("type") == "text"
                )
                or None
            )

    return _event_result_message(raw_event)


def _event_usage(raw_event: dict[str, object]) -> AgentUsage | None:
    usage = raw_event.get("usage")
    message = raw_event.get("message")
    if usage is None and isinstance(message, dict):
        usage = message.get("usage")
    if not isinstance(usage, dict):
        return None

    input_tokens = _int_value(usage.get("input_tokens"))
    output_tokens = _int_value(usage.get("output_tokens"))
    total_tokens = _int_value(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens

    return AgentUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _str_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int_value(value: object) -> int | None:
    return value if isinstance(value, int) else None
