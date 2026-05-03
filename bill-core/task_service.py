from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from schemas import TaskCreateResponse

_tasks_ref: list[dict[str, Any]] | None = None
_append_task_log: Callable[..., None] | None = None
_save_task_db: Callable[[dict[str, Any]], None] | None = None
_logger: Any = None


def configure_task_runtime(
    tasks_ref: list[dict[str, Any]],
    append_task_log: Callable[..., None],
    save_task_db: Callable[[dict[str, Any]], None],
    logger: Any,
) -> None:
    global _tasks_ref, _append_task_log, _save_task_db, _logger
    _tasks_ref = tasks_ref
    _append_task_log = append_task_log
    _save_task_db = save_task_db
    _logger = logger


def create_task_record(normalized_payload: dict[str, Any]) -> TaskCreateResponse:
    if _tasks_ref is None or _append_task_log is None or _save_task_db is None or _logger is None:
        raise RuntimeError("Task service runtime is not configured")

    task_id = str(uuid4())
    task = {
        "id": task_id,
        "payload": normalized_payload,
        "status": "queued",
        "assigned_machine_uuid": None,
        "result_json": None,
        "error": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "completed_at": None,
        "logs": [],
    }
    _tasks_ref.append(task)
    _append_task_log(task, f"Task created with type={normalized_payload.get('task_type', 'unknown')}")
    _save_task_db(task)
    _logger.info("Task created: id=%s task_type=%s", task_id, normalized_payload.get("task_type", "unknown"))
    return TaskCreateResponse(id=task_id, status="queued")
