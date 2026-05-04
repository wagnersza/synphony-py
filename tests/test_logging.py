from __future__ import annotations

import io
import json
from pathlib import Path

from synphony.logging import configure_logging, get_logger


def test_configure_logging_emits_structured_json_to_stream() -> None:
    stream = io.StringIO()
    configure_logging(stream=stream)

    get_logger("worker").info(
        "session started",
        extra={"issue_id": "10001", "issue_identifier": "DEMO-1", "provider": "codex"},
    )

    record = json.loads(stream.getvalue())
    assert record["level"] == "INFO"
    assert record["logger"] == "synphony.worker"
    assert record["message"] == "session started"
    assert record["issue_id"] == "10001"
    assert record["issue_identifier"] == "DEMO-1"
    assert record["provider"] == "codex"


def test_configure_logging_writes_file_when_logs_root_is_set(tmp_path: Path) -> None:
    log_path = configure_logging(logs_root=tmp_path, stream=io.StringIO())

    get_logger("cli").error("startup failed", extra={"error_code": "config_validation_error"})

    assert log_path == tmp_path / "synphony.log"
    assert log_path is not None
    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record["message"] == "startup failed"
    assert record["error_code"] == "config_validation_error"
