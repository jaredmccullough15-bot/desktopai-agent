"""
task_store.py — Durable task persistence helpers for Bill Core.

Purpose
-------
Provides DB-backed read functions so that the task queue survives
Beanstalk restarts.

Architecture
------------
The existing main.py already writes every task mutation to the DB via
`save_task_db()` (in db_writes.py).  The missing piece was startup:
after a restart the in-memory `tasks` list was empty even though the DB
had all the task history.

This module supplies:
  - load_tasks_from_db()    → called once at startup to repopulate tasks
  - list_tasks_db()         → direct DB read for the /api/tasks endpoint
                              (used as a fallback when in-memory list is empty)

Stale-task requeue policy
-------------------------
A task that was "assigned", "running", or "recovering" when the process
died is assumed to have been orphaned.  After STALE_ASSIGNED_MINUTES it
is returned to "queued" so a worker can pick it up again on the next poll.

The caller is responsible for persisting any requeued task back to the DB
(the _requeued_on_startup flag on the returned dict signals this).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("bill-core.task_store")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Tasks in "assigned"/"running"/"recovering" state older than this many minutes
# are considered orphaned and get requeued on the next startup.
STALE_ASSIGNED_MINUTES: int = int(
    os.getenv("BILL_CORE_STALE_TASK_MINUTES", "120")
)

# Load tasks created within this many days (prevents loading months of history).
TASK_LOAD_WINDOW_DAYS: int = int(
    os.getenv("BILL_CORE_TASK_LOAD_DAYS", "7")
)

# Statuses that need no action on startup (already terminal).
_TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "canceled", "cancelled"}
)

# Statuses that indicate the task was mid-flight when the process died.
_STALE_CANDIDATE_STATUSES: frozenset[str] = frozenset(
    {"assigned", "running", "recovering"}
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_iso(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string; return None if invalid."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _append_startup_log(task: dict[str, Any], message: str, level: str = "info") -> None:
    """Add a startup-event log entry to the task's logs list."""
    if not isinstance(task.get("logs"), list):
        task["logs"] = []
    task["logs"].append({
        "message": message,
        "level": level,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "startup_recovery",
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_tasks_from_db(
    stale_assigned_minutes: int = STALE_ASSIGNED_MINUTES,
    window_days: int = TASK_LOAD_WINDOW_DAYS,
) -> list[dict[str, Any]]:
    """Load tasks from the database into memory on startup.

    Returns a list of task dicts ready to be inserted into the global
    `tasks` list.  Tasks that were stale-assigned are requeued.

    Tasks with `_requeued_on_startup=True` must be saved back to the DB
    by the caller (to record the status change durably).

    Never raises — returns an empty list on any error.
    """
    try:
        return _load_tasks_from_db_inner(stale_assigned_minutes, window_days)
    except Exception as exc:
        logger.warning("task_store.load_tasks_from_db failed (non-fatal): %s", exc)
        return []


def _load_tasks_from_db_inner(
    stale_assigned_minutes: int,
    window_days: int,
) -> list[dict[str, Any]]:
    from db import SessionLocal
    from models_db import Task as TaskRow

    cutoff = datetime.utcnow() - timedelta(days=window_days)
    stale_threshold = datetime.utcnow() - timedelta(minutes=stale_assigned_minutes)

    results: list[dict[str, Any]] = []
    requeued_count = 0
    skipped_count = 0

    with SessionLocal() as session:
        rows = (
            session.query(TaskRow)
            .filter(TaskRow.created_at >= cutoff)
            .order_by(TaskRow.created_at.asc())  # oldest first → natural queue order
            .all()
        )

        for row in rows:
            if not row.data:
                skipped_count += 1
                continue
            try:
                task: dict[str, Any] = json.loads(row.data)
            except (json.JSONDecodeError, ValueError):
                skipped_count += 1
                continue

            # Ensure core fields are present (defensive — data column should be complete)
            if not task.get("id"):
                task["id"] = row.id
            if not task.get("status"):
                task["status"] = row.status or "queued"

            status = str(task.get("status") or "").lower()

            # Requeue stale mid-flight tasks
            if status in _STALE_CANDIDATE_STATUSES:
                created_at = _parse_iso(task.get("created_at"))
                updated_at = _parse_iso(task.get("updated_at"))
                # Use updated_at as the staleness reference if available
                ref_time = updated_at or created_at
                if ref_time is not None and ref_time < stale_threshold:
                    original_status = status
                    task["status"] = "queued"
                    task["assigned_machine_uuid"] = None
                    task["updated_at"] = datetime.utcnow().isoformat()
                    _append_startup_log(
                        task,
                        f"Requeued on startup: was '{original_status}' "
                        f"(stale for >{stale_assigned_minutes}min). "
                        f"Original assigned_machine_uuid: "
                        f"{task.get('assigned_machine_uuid') or 'none'}",
                        level="warning",
                    )
                    task["_requeued_on_startup"] = True
                    requeued_count += 1
                    logger.warning(
                        "TASK_STARTUP_REQUEUE id=%s original_status=%s updated_at=%s",
                        task["id"],
                        original_status,
                        ref_time.isoformat() if ref_time else "unknown",
                    )

            results.append(task)

    logger.info(
        "TASK_STARTUP_RECOVERY loaded=%d requeued=%d skipped=%d window_days=%d",
        len(results),
        requeued_count,
        skipped_count,
        window_days,
    )
    return results


def list_tasks_db(limit: int = 20) -> list[dict[str, Any]]:
    """Read the most recent tasks directly from the DB (ordered by created_at desc).

    Used as a fallback by the /api/tasks endpoint when the in-memory list
    is empty (e.g., a request arrives before startup loading completes).

    Never raises — returns an empty list on any error.
    """
    try:
        return _list_tasks_db_inner(limit)
    except Exception as exc:
        logger.warning("task_store.list_tasks_db failed (non-fatal): %s", exc)
        return []


def _list_tasks_db_inner(limit: int) -> list[dict[str, Any]]:
    from db import SessionLocal
    from models_db import Task as TaskRow

    safe_limit = max(1, min(limit, 500))
    results: list[dict[str, Any]] = []

    with SessionLocal() as session:
        rows = (
            session.query(TaskRow)
            .order_by(TaskRow.created_at.desc())
            .limit(safe_limit)
            .all()
        )
        for row in rows:
            if not row.data:
                continue
            try:
                task = json.loads(row.data)
                results.append(task)
            except (json.JSONDecodeError, ValueError):
                continue

    return results


def get_task_db(task_id: str) -> dict[str, Any] | None:
    """Look up a single task by ID directly from the DB.

    Returns None if not found or on any error.
    """
    try:
        return _get_task_db_inner(task_id)
    except Exception as exc:
        logger.warning("task_store.get_task_db failed id=%s: %s", task_id, exc)
        return None


def _get_task_db_inner(task_id: str) -> dict[str, Any] | None:
    from db import SessionLocal
    from models_db import Task as TaskRow

    with SessionLocal() as session:
        row = session.get(TaskRow, task_id)
        if row is None or not row.data:
            return None
        try:
            return json.loads(row.data)
        except (json.JSONDecodeError, ValueError):
            return None
