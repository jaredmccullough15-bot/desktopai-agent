from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from schemas import TaskCreateResponse

_tasks_ref: list[dict[str, Any]] | None = None
_append_task_log: Callable[..., None] | None = None
_save_task_db: Callable[[dict[str, Any]], None] | None = None
_logger: Any = None


def _normalize_run_mode(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_smart_sherpa_payload(payload: dict[str, Any] | None) -> bool:
    payload = payload or {}
    workflow_hint = str(payload.get("workflow_id") or payload.get("workflow_name") or "").strip().lower()
    task_type = str(payload.get("task_type") or "").strip().lower()
    return workflow_hint == "smart_sherpa_sync" or task_type == "smart_sherpa_sync"


def _normalize_smart_sherpa_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload or {})
    if not _is_smart_sherpa_payload(normalized):
        return normalized

    normalized["task_type"] = "smart_sherpa_sync"
    normalized["workflow_id"] = "smart_sherpa_sync"
    normalized["workflow_name"] = "smart_sherpa_sync"
    normalized["attach_to_existing"] = True
    normalized["require_existing_page"] = True
    normalized["allow_launch_fallback"] = False
    normalized["browser_profile_policy"] = "attach_existing_debug"
    return normalized


def _log_smart_sherpa_payload(payload: dict[str, Any]) -> None:
    if _logger is None:
        return
    source_record = payload.get("source_record") if isinstance(payload.get("source_record"), dict) else {}
    target_contact = payload.get("target_contact") if isinstance(payload.get("target_contact"), dict) else {}
    run_mode = (
        _normalize_run_mode(payload.get("run_mode"))
        or _normalize_run_mode(source_record.get("run_mode"))
        or _normalize_run_mode(target_contact.get("run_mode"))
        or "client"
    )
    _logger.info(
        "SMART_SHERPA_FINAL_PAYLOAD attach_to_existing=%s require_existing_page=%s allow_launch_fallback=%s run_mode=%s",
        payload.get("attach_to_existing"),
        payload.get("require_existing_page"),
        payload.get("allow_launch_fallback"),
        run_mode,
    )


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

    normalized_payload = _normalize_smart_sherpa_payload(normalized_payload)
    if _is_smart_sherpa_payload(normalized_payload):
        _log_smart_sherpa_payload(normalized_payload)

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
