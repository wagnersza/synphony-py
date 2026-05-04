"""Codex app-server backend implementation."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, TextIO

from synphony.agents.base import AgentEventCallback, AgentTurnInput, AgentTurnResult
from synphony.errors import AgentNotFoundError, AgentProtocolError, AgentTimeoutError
from synphony.models import AgentEvent, AgentUsage, build_session_id

JsonObject = dict[str, Any]

_INITIALIZE_ID = 1
_THREAD_START_ID = 2
_DEFAULT_READ_TIMEOUT_MS = 30_000
_DEFAULT_TURN_TIMEOUT_MS = 3_600_000
_NON_INTERACTIVE_TOOL_OUTPUT = "This synphony run does not expose client-side Codex tools yet."


@dataclass(slots=True)
class _CodexSession:
    process: subprocess.Popen[str]
    stdout_lines: queue.Queue[str | None]
    stderr_lines: list[str]
    thread_id: str
    workspace_path: str
    approval_policy: str | Mapping[str, Any] | None
    turn_sandbox_policy: Mapping[str, Any] | str | None
    next_request_id: int = 3
    session_ids: set[str] = field(default_factory=set)


class CodexBackend:
    """JSON-line client for `codex app-server` over stdio."""

    provider = "codex"

    def __init__(
        self,
        *,
        command: str = "codex app-server",
        approval_policy: str | Mapping[str, Any] | None = None,
        thread_sandbox: str | Mapping[str, Any] | None = None,
        turn_sandbox_policy: Mapping[str, Any] | str | None = None,
        read_timeout_ms: int = _DEFAULT_READ_TIMEOUT_MS,
        turn_timeout_ms: int = _DEFAULT_TURN_TIMEOUT_MS,
    ) -> None:
        self.command = command
        self.approval_policy = approval_policy
        self.thread_sandbox = thread_sandbox
        self.turn_sandbox_policy = turn_sandbox_policy
        self.read_timeout_ms = read_timeout_ms
        self.turn_timeout_ms = turn_timeout_ms
        self._sessions: dict[str, _CodexSession] = {}

    def start_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        self._validate_turn(turn)
        session = self._launch_session(turn)
        try:
            return self._run_turn(session, turn, include_session_started=True)
        except Exception:
            self._stop_process(session)
            raise

    def continue_session(self, turn: AgentTurnInput) -> AgentTurnResult:
        self._validate_turn(turn)
        if turn.session_id is None:
            raise AgentProtocolError(
                "codex continuation requires an existing session_id",
                details={"provider": self.provider},
            )
        session = self._get_session(turn.session_id)
        try:
            return self._run_turn(session, turn, include_session_started=False)
        except Exception:
            self._stop_process(session)
            raise

    def stop_session(self, session_id: str, *, timeout: timedelta | None = None) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            return
        self._stop_process(session, timeout=timeout)

    def _launch_session(self, turn: AgentTurnInput) -> _CodexSession:
        process = self._start_process(turn.workspace.path)
        stdout_lines: queue.Queue[str | None] = queue.Queue()
        stderr_lines: list[str] = []
        assert process.stdout is not None
        assert process.stderr is not None
        threading.Thread(
            target=_pump_stdout,
            args=(process.stdout, stdout_lines),
            daemon=True,
        ).start()
        threading.Thread(
            target=_pump_stderr,
            args=(process.stderr, stderr_lines),
            daemon=True,
        ).start()

        session = _CodexSession(
            process=process,
            stdout_lines=stdout_lines,
            stderr_lines=stderr_lines,
            thread_id="",
            workspace_path=turn.workspace.path,
            approval_policy=self.approval_policy,
            turn_sandbox_policy=self.turn_sandbox_policy,
        )
        try:
            self._initialize(session)
            session.thread_id = self._start_thread(session)
        except Exception:
            self._stop_process(session)
            raise
        return session

    def _start_process(self, workspace_path: str) -> subprocess.Popen[str]:
        try:
            return subprocess.Popen(
                ["bash", "-lc", self.command],
                cwd=workspace_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise AgentNotFoundError(
                "bash was not found while starting codex app-server",
                details={"provider": self.provider, "command": self.command},
            ) from exc
        except OSError as exc:
            raise AgentProtocolError(
                "failed to start codex app-server",
                details={"provider": self.provider, "command": self.command, "reason": str(exc)},
            ) from exc

    def _initialize(self, session: _CodexSession) -> None:
        self._send(
            session,
            {
                "method": "initialize",
                "id": _INITIALIZE_ID,
                "params": {
                    "capabilities": {"experimentalApi": True},
                    "clientInfo": {
                        "name": "synphony-orchestrator",
                        "title": "Synphony Orchestrator",
                        "version": "0.1.0",
                    },
                },
            },
        )
        self._await_response(session, _INITIALIZE_ID, self.read_timeout_ms)
        self._send(session, {"method": "initialized", "params": {}})

    def _start_thread(self, session: _CodexSession) -> str:
        params: JsonObject = {"cwd": session.workspace_path}
        if self.approval_policy is not None:
            params["approvalPolicy"] = self.approval_policy
        if self.thread_sandbox is not None:
            params["sandbox"] = self.thread_sandbox

        self._send(session, {"method": "thread/start", "id": _THREAD_START_ID, "params": params})
        result = self._await_response(session, _THREAD_START_ID, self.read_timeout_ms)
        thread_payload = result.get("thread")
        thread_id = thread_payload.get("id") if isinstance(thread_payload, dict) else None
        if not isinstance(thread_id, str):
            raise AgentProtocolError(
                "codex thread/start response did not include a thread id",
                details={"provider": self.provider, "payload": result},
            )
        return thread_id

    def _run_turn(
        self,
        session: _CodexSession,
        turn: AgentTurnInput,
        *,
        include_session_started: bool,
    ) -> AgentTurnResult:
        request_id = session.next_request_id
        session.next_request_id += 1
        params: JsonObject = {
            "threadId": session.thread_id,
            "input": [{"type": "text", "text": turn.prompt}],
            "cwd": session.workspace_path,
            "title": f"{turn.issue.identifier}: {turn.issue.title}",
        }
        if session.approval_policy is not None:
            params["approvalPolicy"] = session.approval_policy
        if session.turn_sandbox_policy is not None:
            params["sandboxPolicy"] = session.turn_sandbox_policy

        self._send(session, {"method": "turn/start", "id": request_id, "params": params})
        result = self._await_response(session, request_id, self.read_timeout_ms)
        turn_payload = result.get("turn")
        if not isinstance(turn_payload, dict) or not isinstance(turn_payload.get("id"), str):
            raise AgentProtocolError(
                "codex turn/start response did not include a turn id",
                details={"provider": self.provider, "payload": result},
            )

        turn_id = turn_payload["id"]
        session_id = build_session_id(
            provider=self.provider, thread_id=session.thread_id, turn_id=turn_id
        )
        session.session_ids.add(session_id)
        self._sessions[session_id] = session

        events: list[AgentEvent] = []
        if include_session_started:
            self._emit_event(
                events,
                turn.on_event,
                session_id=session_id,
                kind="session.started",
                turn_id=turn_id,
                raw={"thread_id": session.thread_id},
            )
        self._emit_event(
            events,
            turn.on_event,
            session_id=session_id,
            kind="turn.started",
            turn_id=turn_id,
        )

        timeout_ms = _turn_timeout_ms(turn, self.turn_timeout_ms)
        self._await_turn_completion(
            session,
            session_id=session_id,
            turn_id=turn_id,
            timeout_ms=timeout_ms,
            events=events,
            on_event=turn.on_event,
        )
        return AgentTurnResult(session_id=session_id, turn_id=turn_id, events=tuple(events))

    def _await_turn_completion(
        self,
        session: _CodexSession,
        *,
        session_id: str,
        turn_id: str,
        timeout_ms: int,
        events: list[AgentEvent],
        on_event: AgentEventCallback | None,
    ) -> None:
        deadline = time.monotonic() + (timeout_ms / 1000)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentTimeoutError(provider=self.provider, timeout_ms=timeout_ms)
            try:
                payload = self._read_json_message(session, int(remaining * 1000))
            except AgentTimeoutError as exc:
                raise AgentTimeoutError(provider=self.provider, timeout_ms=timeout_ms) from exc

            method = payload.get("method")
            if not isinstance(method, str):
                self._emit_event(
                    events,
                    on_event,
                    session_id=session_id,
                    kind="other_message",
                    turn_id=turn_id,
                    raw=payload,
                )
                continue

            if method == "turn/completed":
                self._emit_payload_event(
                    events, on_event, session_id, turn_id, "turn.completed", payload
                )
                return

            if method in {"turn/failed", "turn/cancelled"}:
                event_kind = method.replace("/", ".")
                self._emit_payload_event(events, on_event, session_id, turn_id, event_kind, payload)
                raise AgentProtocolError(
                    "codex turn ended unsuccessfully",
                    details={"provider": self.provider, "event": event_kind, "payload": payload},
                )

            if _requires_operator_input(method, payload):
                self._emit_payload_event(
                    events,
                    on_event,
                    session_id,
                    turn_id,
                    "turn.input_required",
                    payload,
                )
                raise AgentProtocolError(
                    "codex turn requested operator input",
                    details={
                        "provider": self.provider,
                        "event": "turn.input_required",
                        "payload": payload,
                    },
                )

            if _is_approval_request(method):
                self._handle_approval_request(
                    session, events, on_event, session_id, turn_id, payload
                )
                continue

            if method == "item/tool/call":
                self._handle_unsupported_tool_call(
                    session,
                    events,
                    on_event,
                    session_id,
                    turn_id,
                    payload,
                )
                continue

            self._emit_payload_event(
                events,
                on_event,
                session_id,
                turn_id,
                method.replace("/", "."),
                payload,
            )

    def _handle_approval_request(
        self,
        session: _CodexSession,
        events: list[AgentEvent],
        on_event: AgentEventCallback | None,
        session_id: str,
        turn_id: str,
        payload: JsonObject,
    ) -> None:
        request_id = payload.get("id")
        if session.approval_policy == "never" and request_id is not None:
            self._send(session, {"id": request_id, "result": {"decision": "acceptForSession"}})
            self._emit_payload_event(
                events,
                on_event,
                session_id,
                turn_id,
                "approval.auto_approved",
                payload,
            )
            return

        self._emit_payload_event(
            events, on_event, session_id, turn_id, "approval.required", payload
        )
        raise AgentProtocolError(
            "codex turn requested approval",
            details={"provider": self.provider, "event": "approval.required", "payload": payload},
        )

    def _handle_unsupported_tool_call(
        self,
        session: _CodexSession,
        events: list[AgentEvent],
        on_event: AgentEventCallback | None,
        session_id: str,
        turn_id: str,
        payload: JsonObject,
    ) -> None:
        request_id = payload.get("id")
        if request_id is not None:
            self._send(
                session,
                {
                    "id": request_id,
                    "result": {
                        "success": False,
                        "output": _NON_INTERACTIVE_TOOL_OUTPUT,
                        "contentItems": [
                            {"type": "inputText", "text": _NON_INTERACTIVE_TOOL_OUTPUT}
                        ],
                    },
                },
            )
        self._emit_payload_event(events, on_event, session_id, turn_id, "tool_call.failed", payload)

    def _await_response(
        self,
        session: _CodexSession,
        request_id: int,
        timeout_ms: int,
    ) -> JsonObject:
        while True:
            payload = self._read_json_message(session, timeout_ms)
            if payload.get("id") != request_id:
                continue
            if "error" in payload:
                raise AgentProtocolError(
                    "codex app-server returned an error response",
                    details={"provider": self.provider, "payload": payload},
                )
            result = payload.get("result")
            if not isinstance(result, dict):
                raise AgentProtocolError(
                    "codex app-server response did not include an object result",
                    details={"provider": self.provider, "payload": payload},
                )
            return result

    def _read_json_message(self, session: _CodexSession, timeout_ms: int) -> JsonObject:
        deadline = time.monotonic() + (timeout_ms / 1000)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentTimeoutError(provider=self.provider, timeout_ms=timeout_ms)

            try:
                line = session.stdout_lines.get(timeout=remaining)
            except queue.Empty as exc:
                raise AgentTimeoutError(provider=self.provider, timeout_ms=timeout_ms) from exc

            if line is None:
                raise AgentProtocolError(
                    "codex app-server exited before completing the protocol exchange",
                    details={
                        "provider": self.provider,
                        "exit_code": session.process.poll(),
                        "stderr": _stderr_excerpt(session.stderr_lines),
                    },
                )

            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload

    def _send(self, session: _CodexSession, payload: JsonObject) -> None:
        if session.process.stdin is None:
            raise AgentProtocolError(
                "codex app-server stdin is unavailable",
                details={"provider": self.provider},
            )
        try:
            session.process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
            session.process.stdin.flush()
        except BrokenPipeError as exc:
            raise AgentProtocolError(
                "codex app-server closed stdin",
                details={
                    "provider": self.provider,
                    "stderr": _stderr_excerpt(session.stderr_lines),
                },
            ) from exc

    def _emit_payload_event(
        self,
        events: list[AgentEvent],
        on_event: AgentEventCallback | None,
        session_id: str,
        turn_id: str,
        kind: str,
        payload: JsonObject,
    ) -> None:
        params = payload.get("params")
        message = None
        if isinstance(params, dict) and isinstance(params.get("message"), str):
            message = params["message"]
        self._emit_event(
            events,
            on_event,
            session_id=session_id,
            kind=kind,
            turn_id=turn_id,
            message=message,
            usage=_extract_usage(payload),
            rate_limits=_extract_rate_limits(payload),
            raw=payload,
        )

    def _emit_event(
        self,
        events: list[AgentEvent],
        on_event: AgentEventCallback | None,
        *,
        session_id: str,
        kind: str,
        turn_id: str | None = None,
        message: str | None = None,
        usage: AgentUsage | None = None,
        rate_limits: dict[str, Any] | None = None,
        raw: JsonObject | None = None,
    ) -> None:
        event = AgentEvent(
            provider=self.provider,
            session_id=session_id,
            kind=kind,
            occurred_at=AgentTurnResult.now(),
            turn_id=turn_id,
            message=message,
            usage=usage,
            rate_limits=rate_limits or {},
            raw=raw or {},
        )
        events.append(event)
        if on_event is not None:
            on_event(event)

    def _get_session(self, session_id: str) -> _CodexSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise AgentProtocolError(
                "unknown codex session_id",
                details={"provider": self.provider, "session_id": session_id},
            ) from exc

    def _stop_process(self, session: _CodexSession, *, timeout: timedelta | None = None) -> None:
        for session_id in tuple(session.session_ids):
            self._sessions.pop(session_id, None)
        if session.process.poll() is not None:
            return

        wait_seconds = timeout.total_seconds() if timeout is not None else 1.0
        try:
            if session.process.stdin is not None:
                session.process.stdin.close()
        except OSError:
            pass
        session.process.terminate()
        try:
            session.process.wait(timeout=wait_seconds)
        except subprocess.TimeoutExpired:
            session.process.kill()
            session.process.wait(timeout=wait_seconds)

    def _validate_turn(self, turn: AgentTurnInput) -> None:
        if turn.provider != self.provider:
            raise AgentProtocolError(
                "codex backend received a turn for a different provider",
                details={"provider": self.provider, "turn_provider": turn.provider},
            )


def _pump_stdout(stream: TextIO, lines: queue.Queue[str | None]) -> None:
    try:
        for line in stream:
            lines.put(line)
    finally:
        lines.put(None)


def _pump_stderr(stream: TextIO, lines: list[str]) -> None:
    for line in stream:
        lines.append(line)


def _turn_timeout_ms(turn: AgentTurnInput, default_timeout_ms: int) -> int:
    if turn.timeout is None:
        return default_timeout_ms
    return int(turn.timeout.total_seconds() * 1000)


def _extract_usage(payload: JsonObject) -> AgentUsage | None:
    usage = _nested_mapping(payload, "usage")
    if usage is None:
        params = payload.get("params")
        if isinstance(params, dict):
            usage = _nested_mapping(params, "usage")
    if usage is None:
        return None

    return AgentUsage(
        input_tokens=_optional_int(usage, "input_tokens", "inputTokens", "prompt_tokens"),
        output_tokens=_optional_int(usage, "output_tokens", "outputTokens", "completion_tokens"),
        total_tokens=_optional_int(usage, "total_tokens", "totalTokens", "total"),
    )


def _extract_rate_limits(payload: JsonObject) -> dict[str, Any]:
    rate_limits = _nested_mapping(payload, "rate_limits", "rateLimits")
    if rate_limits is None:
        params = payload.get("params")
        if isinstance(params, dict):
            rate_limits = _nested_mapping(params, "rate_limits", "rateLimits")
    return dict(rate_limits) if rate_limits is not None else {}


def _nested_mapping(mapping: Mapping[str, Any], *keys: str) -> Mapping[str, Any] | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, Mapping):
            return value
    return None


def _optional_int(mapping: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int):
            return value
    return None


def _is_approval_request(method: str) -> bool:
    return method in {
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "execCommandApproval",
        "applyPatchApproval",
    }


def _requires_operator_input(method: str, payload: JsonObject) -> bool:
    if method in {
        "item/tool/requestUserInput",
        "turn/input_required",
        "turn/needs_input",
        "turn/need_input",
        "turn/request_input",
        "turn/request_response",
        "turn/provide_input",
        "turn/approval_required",
    }:
        return True

    params = payload.get("params")
    return _payload_requires_input(payload) or (
        isinstance(params, dict) and _payload_requires_input(params)
    )


def _payload_requires_input(payload: Mapping[str, Any]) -> bool:
    return (
        payload.get("requiresInput") is True
        or payload.get("needsInput") is True
        or payload.get("input_required") is True
        or payload.get("inputRequired") is True
        or payload.get("type") in {"input_required", "needs_input"}
    )


def _stderr_excerpt(lines: list[str]) -> str:
    return "".join(lines)[-1000:]
