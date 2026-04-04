import logging
import os
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.schemas import (
    BrainCommandRequest,
    BrainCommandResponse,
    MachineRecord,
    ProcedureRunRequest,
    ProcedureTemplate,
    TaskCompleteRequest,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskFailRequest,
    TaskRecord,
    WorkflowRecord,
    WorkerUpdateInstruction,
    WorkerUpdateCheckResponse,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerRegisterResponse,
)

app = FastAPI(title="bill-core", version="0.1.0")


def _split_csv_env(name: str) -> list[str]:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


default_allow_origins = [
    "https://core.bill-core.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3002",
]
env_allow_origins = _split_csv_env("BILL_CORE_CORS_ALLOW_ORIGINS")
allow_origins = []
for origin in (default_allow_origins + env_allow_origins):
    if origin not in allow_origins:
        allow_origins.append(origin)

allow_origin_regex = (
    os.getenv("BILL_CORE_CORS_ALLOW_ORIGIN_REGEX")
    or r"^https?://(localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[0-1])(?:\.\d{1,3}){2}|[a-z0-9-]+\.trycloudflare\.com)(:\d+)?$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bill-core")

SERVER_HOST = (os.getenv("BILL_CORE_HOST") or "0.0.0.0").strip() or "0.0.0.0"
SERVER_PORT = (os.getenv("BILL_CORE_PORT") or "8000").strip() or "8000"

WORKERS_STORE_PATH = Path(os.getenv("BILL_CORE_WORKERS_STORE") or (Path(__file__).resolve().parent / "workers_store.json"))
_workers_lock = threading.Lock()


def _load_workers_store() -> dict[str, dict]:
    if not WORKERS_STORE_PATH.exists():
        return {}
    try:
        raw = json.loads(WORKERS_STORE_PATH.read_text(encoding="utf-8-sig"))
    except Exception as error:
        logger.error("Failed loading workers store %s: %s", WORKERS_STORE_PATH, error)
        return {}
    if not isinstance(raw, dict):
        logger.error("Workers store %s is invalid JSON object", WORKERS_STORE_PATH)
        return {}
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)}


def _save_workers_store() -> None:
    WORKERS_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORKERS_STORE_PATH.write_text(json.dumps(registered_workers, indent=2), encoding="utf-8")
    logger.info("worker store persisted: count=%s path=%s", len(registered_workers), WORKERS_STORE_PATH)


registered_workers: dict[str, dict] = _load_workers_store()
tasks: list[dict] = []

WORKFLOWS_CONFIG_PATH = Path(os.getenv("BILL_CORE_WORKFLOWS_CONFIG") or (Path(__file__).resolve().parent / "workflows_registry.json"))
BRAIN_AUDIT_PATH = Path(os.getenv("BILL_CORE_BRAIN_AUDIT") or (Path(__file__).resolve().parent / "brain_command_audit.json"))

DEFAULT_WORKFLOW_RECORDS: list[dict[str, Any]] = [
    {
        "workflow_name": "smart_sherpa_sync",
        "description": "Process HealthSherpa client list and wait for sync completion.",
        "required_inputs": [],
        "login_or_session_required": True,
        "safe_for_unattended": False,
        "compatible_worker_types": ["interactive_visible"],
        "procedure_name": "smart_sherpa_sync",
    },
    {
        "workflow_name": "marketplace_workflow",
        "description": "Open Marketplace and capture a screenshot for readiness verification.",
        "required_inputs": [],
        "login_or_session_required": False,
        "safe_for_unattended": True,
        "compatible_worker_types": ["interactive_visible", "headless_background"],
        "procedure_name": "marketplace_workflow",
    },
]


@app.on_event("startup")
def log_server_binding() -> None:
    global WORKFLOW_REGISTRY
    WORKFLOW_REGISTRY = _load_workflow_registry()
    logger.info("Server running on: http://%s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("Loaded workflows: %s from %s", len(WORKFLOW_REGISTRY), WORKFLOWS_CONFIG_PATH)
    logger.info("Loaded brain audit entries: %s", len(brain_audit_log))


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw_part in str(version).strip().split("."):
        digits = "".join(ch for ch in raw_part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_newer_version(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def _resolve_worker_package_file() -> Path | None:
    explicit_path = (os.getenv("BILL_WORKER_PACKAGE_FILE") or "").strip()
    package_url = (os.getenv("BILL_WORKER_PACKAGE_URL") or "").strip()

    raw_value = explicit_path or package_url
    if not raw_value:
        return None

    if raw_value.startswith("file://"):
        parsed = urlparse(raw_value)
        parsed_path = unquote(parsed.path or "")
        # On Windows, file:// URLs may parse as /C:/path; strip leading slash.
        if parsed_path.startswith("/") and len(parsed_path) > 2 and parsed_path[2] == ":":
            parsed_path = parsed_path[1:]
        return Path(parsed_path)

    if "://" in raw_value:
        return None

    return Path(raw_value)


def _build_worker_update_instruction(current_version: str, machine_uuid: str) -> WorkerUpdateInstruction:
    latest_version = (os.getenv("BILL_WORKER_LATEST_VERSION") or "").strip()
    package_url = (os.getenv("BILL_WORKER_PACKAGE_PUBLIC_URL") or os.getenv("BILL_WORKER_PACKAGE_URL") or "").strip()
    package_sha256 = (os.getenv("BILL_WORKER_PACKAGE_SHA256") or "").strip() or None
    force_update_enabled = (os.getenv("BILL_WORKER_FORCE_UPDATE") or "").strip().lower() in {"1", "true", "yes", "on"}

    if not latest_version:
        return WorkerUpdateInstruction(
            update_available=False,
            current_version=current_version,
            message="No worker update configured on bill-core",
        )

    if not package_url:
        return WorkerUpdateInstruction(
            update_available=False,
            current_version=current_version,
            latest_version=latest_version,
            message="Worker update configured without package URL",
        )

    update_available = _is_newer_version(latest_version, current_version)
    logger.info(
        "Worker update evaluation: uuid=%s current=%s latest=%s update_available=%s",
        machine_uuid,
        current_version,
        latest_version,
        update_available,
    )

    return WorkerUpdateInstruction(
        update_available=update_available,
        force_update=(force_update_enabled and update_available),
        current_version=current_version,
        latest_version=latest_version,
        package_url=package_url,
        package_sha256=package_sha256,
        message=("Forced update required" if (force_update_enabled and update_available) else ("Update available" if update_available else "Worker is up to date")),
    )


@app.get("/worker/update/package")
def download_worker_update_package() -> FileResponse:
    package_file = _resolve_worker_package_file()
    if package_file is None:
        raise HTTPException(status_code=404, detail="No local worker package configured")

    package_path = package_file.expanduser().resolve()
    if not package_path.exists() or not package_path.is_file():
        raise HTTPException(status_code=404, detail=f"Worker package not found: {package_path}")

    logger.info("Serving worker update package from: %s", package_path)
    return FileResponse(path=package_path, filename=package_path.name, media_type="application/zip")

PROCEDURE_TEMPLATES: dict[str, dict] = {
    "smart_sherpa_sync": {
        "name": "smart_sherpa_sync",
        "task_type": "smart_sherpa_sync",
        "description": "Process HealthSherpa clients and wait for sync completion before moving on.",
        "payload": {
            "task_type": "smart_sherpa_sync",
            "core_driven": True,
            "strict_selectors_only": True,
            "mode": "interactive_visible",
            "attach_to_existing": True,
            "require_existing_page": False,
            "allow_launch_fallback": True,
            "cdp_url": "http://127.0.0.1:9222",
            "start_url": "https://www.healthsherpa.com/agents/jared-chapdelaine-mccullough/clients?_agent_id=jared-chapdelaine-mccullough&ffm_applications[agent_archived]=not_archived&ffm_applications[plan_year][]=2026&ffm_applications[search]=true&term=&renewal=all&desc[]=created_at&agent_id=jared-chapdelaine-mccullough&page=1&per_page=10&exchange=onEx&include_shared_applications=false&include_all_applications=false",
            "view_button_selector": "#applications .MuiDataGrid-row button:has-text('View')||#applications .MuiDataGrid-row a:has-text('View')||#applications .MuiDataGrid-row [role='button']:has-text('View')||#applications [role='row'] button:has-text('View')||#applications [role='row'] a:has-text('View')||#applications [role='row'] [role='button']:has-text('View')||#applications tbody tr button:has-text('View')||#applications tbody tr a:has-text('View')||#applications tbody tr [role='button']:has-text('View')",
            "next_page_selector": "#applications .MuiTablePagination-actions button:nth-child(2)||#applications .MuiTablePagination-actions button:has(svg[data-testid='KeyboardArrowRightIcon'])",
            "sync_complete_text": "Sync Complete||Synced||Successfully synced",
            "per_client_timeout_ms": 20000,
            "page_timeout_ms": 45000,
            "max_clients": 0,
            "max_pages": 0,
            "close_behavior": "auto",
        },
    },
    "marketplace_workflow": {
        "name": "marketplace_workflow",
        "task_type": "browser_workflow",
        "description": "Open Marketplace and capture a validation screenshot.",
        "payload": {
            "task_type": "browser_workflow",
            "mode": "interactive_visible",
            "step_delay_ms": 800,
            "steps": [
                {"action": "open_url", "url": "https://marketplace.cms.gov/"},
                {"action": "wait_for_element", "selector": "body", "timeout_ms": 20000},
                {"action": "take_screenshot", "name": "marketplace-home"},
            ],
        },
    },
}

def _load_workflow_registry() -> list[WorkflowRecord]:
    raw_records: list[dict[str, Any]] = []
    if WORKFLOWS_CONFIG_PATH.exists():
        try:
            loaded = json.loads(WORKFLOWS_CONFIG_PATH.read_text(encoding="utf-8-sig"))
            if isinstance(loaded, list):
                raw_records = [item for item in loaded if isinstance(item, dict)]
        except Exception as error:
            logger.error("Failed to load workflows registry %s: %s", WORKFLOWS_CONFIG_PATH, error)

    if not raw_records:
        raw_records = list(DEFAULT_WORKFLOW_RECORDS)
        WORKFLOWS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        WORKFLOWS_CONFIG_PATH.write_text(json.dumps(raw_records, indent=2), encoding="utf-8")

    records: list[WorkflowRecord] = []
    for item in raw_records:
        try:
            records.append(WorkflowRecord(**item))
        except Exception as error:
            logger.error("Invalid workflow entry skipped: %s (%s)", item, error)

    if not records:
        records = [WorkflowRecord(**item) for item in DEFAULT_WORKFLOW_RECORDS]
    return records


def _load_brain_audit_log() -> list[dict[str, Any]]:
    if not BRAIN_AUDIT_PATH.exists():
        return []
    try:
        loaded = json.loads(BRAIN_AUDIT_PATH.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
    except Exception as error:
        logger.error("Failed to load brain audit log %s: %s", BRAIN_AUDIT_PATH, error)
    return []


def _save_brain_audit_log() -> None:
    BRAIN_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRAIN_AUDIT_PATH.write_text(json.dumps(brain_audit_log[-1000:], indent=2), encoding="utf-8")


WORKFLOW_REGISTRY: list[WorkflowRecord] = _load_workflow_registry()
brain_audit_log: list[dict[str, Any]] = _load_brain_audit_log()


def _append_task_log(task: dict, message: str, level: str = "info") -> None:
    logs = task.setdefault("logs", [])
    logs.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
        }
    )


def _create_task_record(normalized_payload: dict) -> TaskCreateResponse:
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
    tasks.append(task)
    _append_task_log(task, f"Task created with type={normalized_payload.get('task_type', 'unknown')}")
    logger.info("Task created: id=%s task_type=%s", task_id, normalized_payload.get("task_type", "unknown"))
    return TaskCreateResponse(id=task_id, status="queued")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": "0.1.0"}


@app.post("/worker/register", response_model=WorkerRegisterResponse)
def register_worker(payload: WorkerRegisterRequest) -> WorkerRegisterResponse:
    now_iso = datetime.utcnow().isoformat()
    with _workers_lock:
        existing_worker = registered_workers.get(payload.machine_uuid)
        existing = existing_worker is not None
        token = str((existing_worker or {}).get("token") or uuid4())
        registered_workers[payload.machine_uuid] = {
            "machine_name": payload.machine_name,
            "token": token,
            "last_seen": now_iso,
            "status": (existing_worker or {}).get("status") or "idle",
            "worker_version": payload.worker_version or (existing_worker or {}).get("worker_version") or "unknown",
            "execution_mode": payload.execution_mode or (existing_worker or {}).get("execution_mode") or "headless_background",
            "current_task_id": payload.current_task_id,
            "current_step": payload.current_step,
            "created_at": (existing_worker or {}).get("created_at") or now_iso,
            "updated_at": now_iso,
        }
        _save_workers_store()

    logger.info(
        "worker saved to DB: action=%s name=%s uuid=%s version=%s mode=%s",
        "updated" if existing else "created",
        payload.machine_name,
        payload.machine_uuid,
        payload.worker_version,
        payload.execution_mode,
    )
    update_instruction = _build_worker_update_instruction(
        current_version=(payload.worker_version or "0.0.0"),
        machine_uuid=payload.machine_uuid,
    )
    connection_confirmed = not bool(update_instruction.force_update)

    if not connection_confirmed:
        logger.warning(
            "Worker connect blocked pending forced update: name=%s uuid=%s current=%s latest=%s",
            payload.machine_name,
            payload.machine_uuid,
            payload.worker_version,
            update_instruction.latest_version,
        )

    return WorkerRegisterResponse(
        token=token,
        machine_uuid=payload.machine_uuid,
        connection_confirmed=connection_confirmed,
        update=update_instruction,
    )


@app.get("/worker/update/check", response_model=WorkerUpdateCheckResponse)
def worker_update_check(machine_uuid: str, current_version: str) -> WorkerUpdateCheckResponse:
    instruction = _build_worker_update_instruction(current_version=current_version, machine_uuid=machine_uuid)
    return WorkerUpdateCheckResponse(**instruction.model_dump())


@app.post("/worker/heartbeat")
def worker_heartbeat(payload: WorkerHeartbeatRequest) -> dict[str, str]:
    with _workers_lock:
        worker = registered_workers.get(payload.machine_uuid)
        if worker is None:
            logger.warning(
                "Heartbeat rejected for unregistered worker: name=%s uuid=%s status=%s",
                payload.machine_name,
                payload.machine_uuid,
                payload.status,
            )
            raise HTTPException(status_code=400, detail="Worker not registered")

        old_status = worker.get("status")
        old_last_seen = worker.get("last_seen")
        worker["machine_name"] = payload.machine_name
        worker["status"] = payload.status
        worker["last_seen"] = datetime.utcnow().isoformat()
        worker["updated_at"] = datetime.utcnow().isoformat()
        if payload.worker_version:
            worker["worker_version"] = payload.worker_version
        if payload.execution_mode:
            worker["execution_mode"] = payload.execution_mode
        worker["current_task_id"] = payload.current_task_id
        worker["current_step"] = payload.current_step
        _save_workers_store()

    logger.info(
        "worker updated via heartbeat: name=%s uuid=%s status=%s prev_status=%s prev_last_seen=%s",
        payload.machine_name,
        payload.machine_uuid,
        payload.status,
        old_status,
        old_last_seen,
    )
    return {"status": "ok"}


@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(payload: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    normalized_payload = payload.normalized_payload()

    raw_body = await request.json()
    if isinstance(raw_body, dict) and raw_body.get("mode") and "mode" not in normalized_payload:
        normalized_payload["mode"] = raw_body["mode"]
    return _create_task_record(normalized_payload)


@app.get("/api/procedures", response_model=list[ProcedureTemplate])
def list_procedures() -> list[ProcedureTemplate]:
    return [ProcedureTemplate(**template) for template in PROCEDURE_TEMPLATES.values()]


@app.post("/api/procedures/{procedure_name}/run", response_model=TaskCreateResponse)
def run_procedure(procedure_name: str, payload: ProcedureRunRequest) -> TaskCreateResponse:
    template = PROCEDURE_TEMPLATES.get(procedure_name)
    if not template:
        raise HTTPException(status_code=404, detail="Procedure not found")

    normalized_payload = dict(template.get("payload") or {})
    if payload.payload:
        normalized_payload.update(payload.payload)
    if payload.mode:
        normalized_payload["mode"] = payload.mode
    if payload.target_machine_uuid:
        normalized_payload["target_machine_uuid"] = payload.target_machine_uuid

    if "task_type" not in normalized_payload:
        normalized_payload["task_type"] = template.get("task_type")

    return _create_task_record(normalized_payload)


def _worker_is_idle(machine: MachineRecord) -> bool:
    return str(machine.status or "").strip().lower() in {"idle", "ready"}


def _sorted_workers(machines: list[MachineRecord]) -> list[MachineRecord]:
    return sorted(
        machines,
        key=lambda machine: (
            0 if machine.online else 1,
            0 if _worker_is_idle(machine) else 1,
            tuple(-x for x in _version_key(machine.worker_version or "0.0.0")),
            (machine.machine_name or ""),
        ),
    )


def _worker_alias_map(machines: list[MachineRecord]) -> dict[str, MachineRecord]:
    alias_map: dict[str, MachineRecord] = {}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for index, machine in enumerate(_sorted_workers(machines)):
        if index >= len(letters):
            break
        alias_map[f"worker {letters[index].lower()}"] = machine
    return alias_map


def _find_worker_by_hint(machines: list[MachineRecord], hint: str | None) -> MachineRecord | None:
    if not hint:
        return None

    needle = hint.strip().lower()
    if not needle:
        return None

    for machine in machines:
        if (machine.machine_uuid or "").lower() == needle:
            return machine

    for alias, machine in _worker_alias_map(machines).items():
        if needle == alias:
            return machine

    if needle.startswith("worker ") and len(needle.split()) == 2:
        alias_machine = _worker_alias_map(machines).get(needle)
        if alias_machine:
            return alias_machine

    for machine in machines:
        if needle in (machine.machine_name or "").lower():
            return machine

    return None


def _select_best_worker(machines: list[MachineRecord], preferred_uuid: str | None = None) -> MachineRecord | None:
    preferred = _find_worker_by_hint(machines, preferred_uuid)
    if preferred and preferred.online:
        return preferred

    online_idle = [machine for machine in machines if machine.online and _worker_is_idle(machine)]
    if online_idle:
        online_idle.sort(key=lambda machine: _version_key(machine.worker_version or "0.0.0"), reverse=True)
        return online_idle[0]

    online_any = [machine for machine in machines if machine.online]
    if online_any:
        online_any.sort(key=lambda machine: _version_key(machine.worker_version or "0.0.0"), reverse=True)
        return online_any[0]

    return None


def _last_failed_task(target_worker_uuid: str | None = None) -> dict | None:
    for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True):
        if task.get("status") != "failed":
            continue
        if target_worker_uuid and task.get("assigned_machine_uuid") != target_worker_uuid:
            continue
        return task
    return None


def _latest_active_task() -> dict | None:
    active_statuses = {"queued", "assigned", "in_progress", "running"}
    for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True):
        if str(task.get("status") or "").lower() in active_statuses:
            return task
    return None


def _workflow_from_command(command: str) -> str | None:
    lower = command.lower()
    if "healthsherpa" in lower or "sherpa" in lower:
        return "smart_sherpa_sync"
    if "marketplace" in lower:
        return "marketplace_workflow"
    return None


def _parse_limit(command_lower: str, label: str) -> int | None:
    patterns = [
        rf"max(?:imum)?\s+{label}\s*(?:=|to)?\s*(\d+)",
        rf"up to\s+(\d+)\s+{label}",
        rf"first\s+(\d+)\s+{label}",
        rf"(\d+)\s+{label}\s+max",
    ]
    for pattern in patterns:
        match = re.search(pattern, command_lower)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


def _extract_name_with_patterns(command_text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, command_text, flags=re.IGNORECASE)
        if match:
            value = (match.group(1) or "").strip().strip(",.;")
            if value:
                return value
    return None


def _parse_command_parameters(command_text: str) -> dict[str, Any]:
    command_lower = command_text.lower()
    params: dict[str, Any] = {}

    max_clients = _parse_limit(command_lower, r"clients?")
    if max_clients is not None:
        params["max_clients"] = max_clients

    max_pages = _parse_limit(command_lower, r"pages?")
    if max_pages is not None:
        params["max_pages"] = max_pages

    params["retry_failed_only"] = any(
        phrase in command_lower
        for phrase in ["retry failed only", "failed only", "only failed", "retry-only failed"]
    )

    client_name = _extract_name_with_patterns(
        command_text,
        [
            r"\bclient\s+name\s*[:=]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
            r"\bfor\s+client\s+([A-Za-z][A-Za-z .'-]{1,80})",
        ],
    )
    if client_name:
        params["client_name"] = client_name

    household_name = _extract_name_with_patterns(
        command_text,
        [
            r"\bhousehold\s+name\s*[:=]?\s*([A-Za-z][A-Za-z .'-]{1,80})",
            r"\bfor\s+household\s+([A-Za-z][A-Za-z .'-]{1,80})",
        ],
    )
    if household_name:
        params["household_name"] = household_name

    return params


def _create_workflow_task(
    workflow_name: str,
    target_machine_uuid: str | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> TaskCreateResponse:
    workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == workflow_name), None)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Unknown workflow: {workflow_name}")

    procedure_name = workflow.procedure_name or workflow.workflow_name
    template = PROCEDURE_TEMPLATES.get(procedure_name)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Procedure template missing: {procedure_name}")

    normalized_payload = dict(template.get("payload") or {})
    if "task_type" not in normalized_payload:
        normalized_payload["task_type"] = template.get("task_type")
    if extra_payload:
        normalized_payload.update(extra_payload)
    if target_machine_uuid:
        normalized_payload["target_machine_uuid"] = target_machine_uuid

    return _create_task_record(normalized_payload)


def _find_task_by_ref(task_ref: str | None) -> dict | None:
    if not task_ref:
        return None
    needle = task_ref.strip().lower()
    if not needle:
        return None

    for task in tasks:
        task_id = str(task.get("id") or "").lower()
        if task_id == needle or task_id.startswith(needle):
            return task
    return None


def _cancel_task_if_possible(task: dict | None) -> tuple[bool, str]:
    if task is None:
        return False, "Task not found."

    status = str(task.get("status") or "").lower()
    if status in {"completed", "failed", "canceled", "cancelled"}:
        return False, f"Task is already terminal with status={status}."

    task["status"] = "canceled"
    task["updated_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, "Task canceled by orchestration command", level="warning")
    return True, f"Task {task.get('id')} canceled."


def _append_brain_audit(entry: dict[str, Any]) -> None:
    brain_audit_log.append(entry)
    _save_brain_audit_log()


@app.get("/api/workflows", response_model=list[WorkflowRecord])
def list_workflows() -> list[WorkflowRecord]:
    return WORKFLOW_REGISTRY


@app.get("/api/brain/audit")
def list_brain_audit(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    return brain_audit_log[-safe_limit:]


@app.post("/api/brain/command", response_model=BrainCommandResponse)
def brain_command(payload: BrainCommandRequest) -> BrainCommandResponse:
    command_text = (payload.command or "").strip()
    if not command_text:
        raise HTTPException(status_code=400, detail="Command text is required")

    command_lower = command_text.lower()
    machines = list_machines()
    command_params = _parse_command_parameters(command_text)
    selected_worker: MachineRecord | None = None
    task: TaskCreateResponse | None = None
    recognized_intent = "unknown"
    selected_workflow: str | None = None
    before_execution = "I could not map that request yet."
    after_execution = "Try asking for workflows, free workers, or to run a known workflow."
    suggested_next_action: str | None = "Try: 'list workflows' or 'which worker is free?'"
    retry_recommended = False

    worker_hint_match = re.search(r"on worker\s+(.+)$", command_text, flags=re.IGNORECASE)
    worker_hint = worker_hint_match.group(1).strip() if worker_hint_match else None

    if payload.target_machine_uuid:
        selected_worker = _find_worker_by_hint(machines, payload.target_machine_uuid)
    elif worker_hint:
        selected_worker = _find_worker_by_hint(machines, worker_hint)

    if "show online workers" in command_lower or "list online workers" in command_lower:
        recognized_intent = "worker_query"
        online = [machine for machine in _sorted_workers(machines) if machine.online]
        before_execution = "I checked worker heartbeat freshness and status."
        if online:
            summary = "; ".join(
                f"{machine.machine_name} ({machine.machine_uuid}) status={machine.status} version={machine.worker_version}"
                for machine in online[:8]
            )
            after_execution = f"Online workers: {summary}"
            suggested_next_action = "Ask me which worker is free to pick the best idle target."
        else:
            after_execution = "No workers are currently online."
            suggested_next_action = "Check worker connectivity and heartbeat endpoints."

    elif "which worker is free" in command_lower or "which worker is idle" in command_lower or "who is free" in command_lower:
        recognized_intent = "worker_query"
        free_workers = [machine for machine in machines if machine.online and _worker_is_idle(machine)]
        if free_workers:
            free_workers.sort(key=lambda machine: _version_key(machine.worker_version or "0.0.0"), reverse=True)
            top = free_workers[0]
            before_execution = "I checked live workers for online and idle status."
            after_execution = (
                f"{top.machine_name} ({top.machine_uuid}) is free now. "
                f"Version={top.worker_version or 'unknown'} mode={top.execution_mode or 'unknown'}."
            )
            suggested_next_action = f"Run a workflow on {top.machine_name} or target machine_uuid {top.machine_uuid}."
        else:
            online_count = sum(1 for machine in machines if machine.online)
            busy_online = sum(1 for machine in machines if machine.online and not _worker_is_idle(machine))
            before_execution = "I checked live workers for online and idle status."
            after_execution = (
                "No online idle workers were found right now. "
                f"online={online_count} busy_online={busy_online} offline={len(machines) - online_count}."
            )
            suggested_next_action = "Ask me 'show active tasks' or wait for workers to become idle."

    elif "what failed last" in command_lower or "last failed" in command_lower or "show last failed task" in command_lower:
        recognized_intent = "failure_explanation"
        failed = _last_failed_task(selected_worker.machine_uuid if selected_worker else None)
        before_execution = "I reviewed recent task history for failures."
        if failed:
            after_execution = (
                f"Last failed task: {failed.get('id')} type={(failed.get('payload') or {}).get('task_type', 'unknown')} "
                f"worker={failed.get('assigned_machine_uuid') or 'unassigned'} error={failed.get('error') or 'no error text'}"
            )
            retry_recommended = True
            suggested_next_action = "Say 'retry last failed task' to queue it again."
        else:
            after_execution = "I did not find any failed tasks in recent history."
            suggested_next_action = "You can ask me to run a workflow now."

    elif "show active tasks" in command_lower or "what is running now" in command_lower or "current progress" in command_lower:
        recognized_intent = "task_summary"
        active = _latest_active_task()
        before_execution = "I checked the latest queued and running tasks."
        if active:
            after_execution = (
                f"Current active task: {active.get('id')} status={active.get('status')} "
                f"type={(active.get('payload') or {}).get('task_type', 'unknown')} "
                f"assigned_worker={active.get('assigned_machine_uuid') or 'pending assignment'}."
            )
            suggested_next_action = "Ask me which worker is free, cancel task <id>, or what failed last."
        else:
            after_execution = "No queued or running tasks were found."
            suggested_next_action = "Ask me to run a workflow."

    elif "list workflows" in command_lower or "what workflows" in command_lower or "show workflows" in command_lower:
        recognized_intent = "workflow_query"
        before_execution = "I loaded the workflow registry in Bill Core."
        names = ", ".join(record.workflow_name for record in WORKFLOW_REGISTRY)
        after_execution = f"Known workflows: {names}."
        suggested_next_action = "Say 'run smart sherpa sync' or 'run marketplace workflow'."

    elif "retry last failed" in command_lower:
        recognized_intent = "task_summary"
        failed = _last_failed_task(selected_worker.machine_uuid if selected_worker else None)
        before_execution = "I inspected recent failures and prepared a retry plan."
        if failed:
            retry_payload = dict(failed.get("payload") or {})
            if command_params.get("retry_failed_only"):
                retry_payload["retry_failed_only"] = True
            if selected_worker and selected_worker.machine_uuid:
                retry_payload["target_machine_uuid"] = selected_worker.machine_uuid
            task = _create_task_record(retry_payload)
            after_execution = f"Queued retry task {task.id} from failed task {failed.get('id')}."
            suggested_next_action = "Monitor task progress in Recent Tasks."
        else:
            after_execution = "No failed task found to retry."
            suggested_next_action = "Ask me to run a specific workflow instead."

    elif "pause task" in command_lower:
        recognized_intent = "task_summary"
        before_execution = "I checked whether pause is supported by the current task runtime."
        after_execution = "Pause is not currently supported. I can cancel queued or running tasks instead."
        suggested_next_action = "Say 'cancel task <task_id>'."

    elif "cancel task" in command_lower:
        recognized_intent = "task_summary"
        task_id_match = re.search(r"cancel task\s+([a-f0-9-]{6,})", command_lower)
        task_ref = task_id_match.group(1) if task_id_match else None
        before_execution = "I attempted a safe cancellation on the requested task."
        canceled, message = _cancel_task_if_possible(_find_task_by_ref(task_ref))
        after_execution = message
        suggested_next_action = "Use 'show active tasks' to confirm current queue state."
        retry_recommended = not canceled

    elif (
        "refresh healthsherpa sync" in command_lower
        or "run smart sherpa" in command_lower
        or "run marketplace workflow" in command_lower
        or "run workflow" in command_lower
    ):
        recognized_intent = "known_workflow"
        selected_workflow = _workflow_from_command(command_text)
        if not selected_workflow:
            selected_workflow = "smart_sherpa_sync"

        workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == selected_workflow), None)
        required_inputs = list((workflow.required_inputs if workflow else []) or [])
        missing_inputs = [key for key in required_inputs if key not in command_params]

        if missing_inputs:
            before_execution = "I parsed your request and identified a workflow, but required inputs are missing."
            after_execution = f"Please provide required inputs: {', '.join(missing_inputs)}."
            suggested_next_action = (
                f"Try: run {selected_workflow} with "
                + " ".join(f"{name} <value>" for name in missing_inputs)
            )
        else:
            if not selected_worker:
                selected_worker = _select_best_worker(machines, payload.target_machine_uuid)

            if workflow and workflow.login_or_session_required:
                before_execution = (
                    "This workflow requires an authenticated browser/session. "
                    "I cannot fully verify session readiness remotely, so ensure the target worker is logged in first."
                )
            else:
                before_execution = "I parsed your request, selected a workflow, and chose the best available worker."

            if selected_worker:
                extra_payload: dict[str, Any] = {}
                for key in ["max_clients", "max_pages", "retry_failed_only", "client_name", "household_name"]:
                    if key in command_params:
                        extra_payload[key] = command_params[key]

                task = _create_workflow_task(
                    selected_workflow,
                    target_machine_uuid=selected_worker.machine_uuid,
                    extra_payload=extra_payload,
                )
                after_execution = (
                    f"Queued workflow '{selected_workflow}' as task {task.id} on worker "
                    f"{selected_worker.machine_name} ({selected_worker.machine_uuid})."
                )
                if extra_payload:
                    after_execution += f" Parsed parameters: {extra_payload}."
                suggested_next_action = "I recommend watching logs and heartbeats while this task runs."
            else:
                online_count = sum(1 for machine in machines if machine.online)
                busy_online = sum(1 for machine in machines if machine.online and not _worker_is_idle(machine))
                after_execution = (
                    "I could not find an available worker for this workflow. "
                    f"online={online_count}, busy_online={busy_online}, offline={len(machines) - online_count}."
                )
                suggested_next_action = "Ask 'show online workers' or run on a specific worker alias." 

    audit_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "original_user_text": command_text,
        "interpreted_intent": recognized_intent,
        "selected_workflow": selected_workflow,
        "selected_worker": selected_worker.machine_uuid if selected_worker else None,
        "queued_task_id": task.id if task else None,
        "before_execution": before_execution,
        "after_execution": after_execution,
    }
    _append_brain_audit(audit_entry)

    return BrainCommandResponse(
        recognized_intent=recognized_intent,
        command=command_text,
        before_execution=before_execution,
        after_execution=after_execution,
        selected_workflow=selected_workflow,
        selected_worker_uuid=selected_worker.machine_uuid if selected_worker else None,
        selected_worker_name=selected_worker.machine_name if selected_worker else None,
        suggested_next_action=suggested_next_action,
        retry_recommended=retry_recommended,
        task=task,
    )


@app.get("/api/machines", response_model=list[MachineRecord])
def list_machines() -> list[MachineRecord]:
    now = datetime.utcnow()
    machines: list[MachineRecord] = []

    with _workers_lock:
        workers_snapshot = dict(registered_workers)

    for machine_uuid, worker in workers_snapshot.items():
        last_seen = worker.get("last_seen")
        online = False
        if isinstance(last_seen, str):
            try:
                online = (now - datetime.fromisoformat(last_seen)).total_seconds() <= 30
            except ValueError:
                online = False

        machines.append(
            MachineRecord(
                machine_uuid=machine_uuid,
                machine_name=worker.get("machine_name", "unknown"),
                status=worker.get("status", "unknown"),
                worker_version=worker.get("worker_version", "unknown"),
                last_seen=last_seen,
                online=online,
                execution_mode=worker.get("execution_mode", "headless_background"),
                current_task_id=worker.get("current_task_id"),
                current_step=worker.get("current_step"),
            )
        )

    logger.info("number of workers returned to UI: %s", len(machines))
    return machines


@app.get("/worker/debug/list")
def debug_list_workers() -> dict:
    with _workers_lock:
        workers_snapshot = dict(registered_workers)

    workers: list[dict] = []
    for machine_uuid, worker in workers_snapshot.items():
        workers.append(
            {
                "machine_uuid": machine_uuid,
                "machine_name": worker.get("machine_name"),
                "status": worker.get("status"),
                "worker_version": worker.get("worker_version"),
                "execution_mode": worker.get("execution_mode"),
                "last_seen": worker.get("last_seen"),
                "updated_at": worker.get("updated_at"),
            }
        )

    logger.info("debug worker list requested: count=%s", len(workers))
    return {"count": len(workers), "workers": workers}


@app.get("/api/system")
def get_system_status() -> dict:
    machines = list_machines()
    online_count = sum(1 for machine in machines if machine.online)
    return {
        "backend": "ok",
        "machine_count": len(machines),
        "online_count": online_count,
        "offline_count": len(machines) - online_count,
        "task_count": len(tasks),
    }


@app.get("/api/tasks", response_model=list[TaskRecord])
def list_tasks(limit: int = 20) -> list[TaskRecord]:
    safe_limit = max(1, min(limit, 200))
    ordered = sorted(tasks, key=lambda task: task.get("created_at", ""), reverse=True)
    return [TaskRecord(**task) for task in ordered[:safe_limit]]


@app.get("/api/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: str) -> TaskRecord:
    for task in tasks:
        if task["id"] == task_id:
            return TaskRecord(**task)
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/api/tasks/{task_id}/cancel")
def cancel_task(task_id: str) -> dict[str, str]:
    target = _find_task_by_ref(task_id)
    canceled, message = _cancel_task_if_possible(target)
    if not canceled:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "canceled", "message": message}


@app.get("/worker/tasks/next", response_model=TaskRecord | None)
def get_next_task(machine_uuid: str):
    with _workers_lock:
        known_worker = machine_uuid in registered_workers
    if not known_worker:
        raise HTTPException(status_code=400, detail="Worker not registered")

    for task in tasks:
        if task["status"] == "queued":
            target_machine_uuid = str((task.get("payload") or {}).get("target_machine_uuid") or "").strip()
            if target_machine_uuid and target_machine_uuid != machine_uuid:
                continue

            task["status"] = "assigned"
            task["assigned_machine_uuid"] = machine_uuid
            task["updated_at"] = datetime.utcnow().isoformat()
            if target_machine_uuid:
                _append_task_log(
                    task,
                    f"Task assigned to target machine_uuid={machine_uuid} (requested={target_machine_uuid})",
                )
            else:
                _append_task_log(task, f"Task assigned to machine_uuid={machine_uuid}")
            logger.info("Task assigned: id=%s machine_uuid=%s", task["id"], machine_uuid)
            return TaskRecord(**task)

    return None


@app.post("/worker/tasks/{task_id}/complete")
def complete_task(task_id: str, payload: TaskCompleteRequest) -> dict[str, str]:
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = "completed"
            task["assigned_machine_uuid"] = payload.machine_uuid
            task["result_json"] = payload.result_json
            task["updated_at"] = datetime.utcnow().isoformat()
            task["completed_at"] = datetime.utcnow().isoformat()
            _append_task_log(task, f"Task completed by machine_uuid={payload.machine_uuid}")
            logger.info("Task completed: id=%s machine_uuid=%s", task_id, payload.machine_uuid)
            return {"status": "completed"}

    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/worker/tasks/{task_id}/fail")
def fail_task(task_id: str, payload: TaskFailRequest) -> dict[str, str]:
    for task in tasks:
        if task["id"] == task_id:
            task["status"] = "failed"
            task["assigned_machine_uuid"] = payload.machine_uuid
            task["error"] = payload.error
            task["result_json"] = payload.result_json
            task["updated_at"] = datetime.utcnow().isoformat()
            task["completed_at"] = datetime.utcnow().isoformat()
            _append_task_log(task, f"Task failed on machine_uuid={payload.machine_uuid}: {payload.error}", level="error")
            logger.error("Task failed: id=%s machine_uuid=%s error=%s", task_id, payload.machine_uuid, payload.error)
            return {"status": "failed"}

    raise HTTPException(status_code=404, detail="Task not found")
