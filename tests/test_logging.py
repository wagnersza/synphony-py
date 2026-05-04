from __future__ import annotations

import json
import logging
from pathlib import Path

from synphony.errors import ConfigValidationError
from synphony.logging import JsonLogFormatter, configure_logging


def test_json_log_formatter_includes_operator_context_and_error_code() -> None:
    record = logging.LogRecord(
        name="synphony",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="startup failed",
        args=(),
        exc_info=None,
    )
    record.issue_id = "10001"
    record.issue_identifier = "DEMO-1"
    record.session_id = "codex:session"
    record.provider = "codex"
    record.error = ConfigValidationError("bad config")

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["level"] == "ERROR"
    assert payload["message"] == "startup failed"
    assert payload["issue_id"] == "10001"
    assert payload["issue_identifier"] == "DEMO-1"
    assert payload["session_id"] == "codex:session"
    assert payload["provider"] == "codex"
    assert payload["code"] == "config_validation_error"


def test_configure_logging_writes_file_when_logs_root_is_set(tmp_path: Path) -> None:
    logger = configure_logging(logs_root=tmp_path)

    logger.info("daemon started", extra={"provider": "claude"})

    log_file = tmp_path / "synphony.log"
    payload = json.loads(log_file.read_text(encoding="utf-8").splitlines()[0])
    assert payload["message"] == "daemon started"
    assert payload["provider"] == "claude"
