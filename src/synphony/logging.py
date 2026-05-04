"""Structured operator logging for synphony."""

from __future__ import annotations

import json
import logging as stdlib_logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synphony.errors import SynphonyError

_CONTEXT_FIELDS = ("issue_id", "issue_identifier", "session_id", "provider", "retry")


class JsonLogFormatter(stdlib_logging.Formatter):
    """Format logs as one JSON object per line with stable operator context."""

    def format(self, record: stdlib_logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        error = getattr(record, "error", None)
        if isinstance(error, SynphonyError):
            payload["code"] = error.code
            payload["error"] = error.message
            if error.details:
                payload["details"] = error.details
        else:
            code = getattr(record, "code", None)
            if code is not None:
                payload["code"] = code

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, sort_keys=True)


def configure_logging(logs_root: str | Path | None = None) -> stdlib_logging.Logger:
    """Configure and return the package logger."""
    logger = stdlib_logging.getLogger("synphony")
    logger.setLevel(stdlib_logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = JsonLogFormatter()
    stream_handler = stdlib_logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if logs_root is not None:
        root = Path(logs_root)
        root.mkdir(parents=True, exist_ok=True)
        file_handler = stdlib_logging.FileHandler(root / "synphony.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
