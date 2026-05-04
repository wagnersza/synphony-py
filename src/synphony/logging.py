"""Structured logging helpers for operator-facing synphony logs."""

from __future__ import annotations

import json
import logging as stdlib_logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

_LOGGER_NAME = "synphony"
_EXTRA_FIELDS = (
    "issue_id",
    "issue_identifier",
    "session_id",
    "provider",
    "error_code",
    "workspace_path",
)


class JsonFormatter(stdlib_logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in _EXTRA_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True)


def configure_logging(
    *,
    logs_root: str | Path | None = None,
    stream: TextIO | None = None,
    level: int = stdlib_logging.INFO,
) -> Path | None:
    """Configure the synphony logger and optionally write logs to `logs_root`."""
    formatter = JsonFormatter()
    handlers: list[stdlib_logging.Handler] = []

    stream_handler = stdlib_logging.StreamHandler(stream)
    stream_handler.setFormatter(formatter)
    handlers.append(stream_handler)

    log_path: Path | None = None
    if logs_root is not None:
        root = Path(logs_root).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        log_path = root / "synphony.log"
        file_handler = stdlib_logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    logger = stdlib_logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False
    for handler in handlers:
        logger.addHandler(handler)

    return log_path


def get_logger(name: str | None = None) -> stdlib_logging.Logger:
    """Return a child logger under the stable synphony namespace."""
    if name is None:
        return stdlib_logging.getLogger(_LOGGER_NAME)
    return stdlib_logging.getLogger(f"{_LOGGER_NAME}.{name}")
