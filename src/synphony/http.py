"""Optional HTTP status surface for operator visibility."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from synphony.models import Issue, LiveSession, RetryEntry, RuntimeState


def issue_payload(issue: Issue) -> dict[str, str | None]:
    return {
        "id": issue.id,
        "identifier": issue.identifier,
        "title": issue.title,
        "state": issue.state,
        "url": issue.url,
    }


def runtime_state_payload(state: RuntimeState) -> dict[str, Any]:
    return {
        "claimed_issue_ids": sorted(state.claimed_issue_ids),
        "running": [_live_session_payload(session) for session in state.running.values()],
        "retries": [_retry_payload(retry) for retry in state.retries],
    }


class StatusServer:
    """Small stdlib HTTP server for read-only runtime state and refresh nudges."""

    def __init__(
        self,
        *,
        state: RuntimeState,
        port: int,
        on_refresh: Callable[[], None] | None = None,
    ) -> None:
        self._state = state
        self._on_refresh = on_refresh
        self._server = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=1)

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        state = self._state
        on_refresh = self._on_refresh

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/api/v1/state":
                    self._write_json(runtime_state_payload(state))
                    return
                prefix = "/api/v1/"
                if self.path.startswith(prefix):
                    identifier = self.path.removeprefix(prefix)
                    for session in state.running.values():
                        if session.issue.identifier == identifier:
                            self._write_json(issue_payload(session.issue))
                            return
                    self._write_json({"error": "issue not found"}, status=HTTPStatus.NOT_FOUND)
                    return
                self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if self.path == "/api/v1/refresh":
                    if on_refresh is not None:
                        on_refresh()
                    self._write_json({"ok": True})
                    return
                self._write_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

            def log_message(self, format: str, *args: object) -> None:
                return None

            def _write_json(
                self,
                payload: dict[str, Any],
                *,
                status: HTTPStatus = HTTPStatus.OK,
            ) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status.value)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _live_session_payload(session: LiveSession) -> dict[str, Any]:
    return {
        **issue_payload(session.issue),
        "issue_id": session.issue.id,
        "issue_identifier": session.issue.identifier,
        "workspace": session.workspace.path,
        "attempt": session.attempt.attempt,
        "provider": session.provider,
        "session_id": session.session_id,
        "started_at": session.started_at.isoformat(),
        "last_event_at": session.last_event_at.isoformat(),
    }


def _retry_payload(retry: RetryEntry) -> dict[str, Any]:
    return {
        **issue_payload(retry.issue),
        "issue_id": retry.issue.id,
        "issue_identifier": retry.issue.identifier,
        "attempt": retry.attempt.attempt,
        "next_retry_at": retry.next_retry_at.isoformat(),
        "reason": retry.reason,
        "backoff_ms": retry.backoff_ms,
    }
