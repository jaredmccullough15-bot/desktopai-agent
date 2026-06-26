"""
structured_logging.py — JSON structured logging for Bill Core.

Usage:
    from structured_logging import slog
    slog(event="task_created", task_id=task_id, route="/api/tasks", message="Task queued")

Every record is written to the standard Python logger "bill-core.structured"
as a single-line JSON object so it can be forwarded/parsed by log aggregators.

Fields emitted in every record:
    timestamp   ISO-8601 UTC
    level       INFO | WARNING | ERROR | CRITICAL
    event       slug identifying the code path (required)
    request_id  optional correlation id from upstream
    task_id     optional task identifier
    worker_id   optional worker machine_uuid
    route       optional HTTP route or code path label
    message     human-readable description
    metadata    any extra keyword arguments passed to slog()
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

_logger = logging.getLogger("bill-core.structured")


def slog(
    event: str,
    *,
    level: str = "INFO",
    request_id: str | None = None,
    task_id: str | None = None,
    worker_id: str | None = None,
    route: str | None = None,
    message: str = "",
    **metadata: Any,
) -> None:
    """Emit a structured JSON log record.

    Args:
        event:      Required slug identifying the code path, e.g. ``"task_created"``.
        level:      Log level string — INFO, WARNING, ERROR, or CRITICAL.
        request_id: Optional correlation / trace id.
        task_id:    Optional task identifier.
        worker_id:  Optional worker machine_uuid.
        route:      Optional HTTP route or label, e.g. ``"/api/tasks"``.
        message:    Human-readable description.
        **metadata: Arbitrary extra fields included in the ``metadata`` dict.
    """
    record: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level.upper(),
        "event": event,
        "message": message,
    }
    if request_id is not None:
        record["request_id"] = request_id
    if task_id is not None:
        record["task_id"] = task_id
    if worker_id is not None:
        record["worker_id"] = worker_id
    if route is not None:
        record["route"] = route
    if metadata:
        record["metadata"] = metadata

    log_level = getattr(logging, level.upper(), logging.INFO)
    _logger.log(log_level, json.dumps(record, default=str))


def slog_error(event: str, *, exc: Exception | None = None, **kwargs: Any) -> None:
    """Convenience wrapper that emits at ERROR level and includes exception info."""
    if exc is not None:
        kwargs.setdefault("exc_type", type(exc).__name__)
        kwargs.setdefault("exc_message", str(exc))
    slog(event, level="ERROR", **kwargs)


def slog_warning(event: str, **kwargs: Any) -> None:
    """Convenience wrapper that emits at WARNING level."""
    slog(event, level="WARNING", **kwargs)
