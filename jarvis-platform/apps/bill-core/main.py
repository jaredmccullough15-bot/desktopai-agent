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

from app.error_explainer import (
    classify_error,
    generate_explanation,
    build_human_summary,
    find_similar_failure,
    score_confidence,
)
from app.schemas import (
    BrainCommandRequest,
    BrainCommandResponse,
    ConversationPreferenceRecord,
    ConversationPreferenceUpdateRequest,
    GuidedExecutionAnswerRequest,
    GuidedExecutionStartRequest,
    ImprovementProposalRecord,
    InteractivePromptDecisionRequest,
    InteractivePromptRecord,
    MachineRecord,
    OperationalMemoryRecord,
    ProposalFeedbackRequest,
    ProposalStatusUpdateRequest,
    ProcedureRunRequest,
    ProcedureTemplate,
    RunWithImprovementRequest,
    TaskReflectionRecord,
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
    WorkflowSOPSummaryRecord,
    WorkflowSOPUpdateRequest,
    WorkflowLearningCreateRequest,
    WorkflowLearningDraftRecord,
    WorkflowDraftStatusUpdateRequest,
    WorkflowDraftTestRequest,
    WorkflowDraftPublishRequest,
    WorkflowDraftStructureUpdateRequest,
    TeachingSessionQuestion,
    TeachingStepQuestion,
    TeachingSessionAnswerRequest,
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
OP_MEMORY_PATH = Path(os.getenv("BILL_CORE_OPERATIONAL_MEMORY") or (Path(__file__).resolve().parent / "operational_memory.json"))
REFLECTIONS_PATH = Path(os.getenv("BILL_CORE_REFLECTIONS") or (Path(__file__).resolve().parent / "task_reflections.json"))
PROPOSALS_PATH = Path(os.getenv("BILL_CORE_PROPOSALS") or (Path(__file__).resolve().parent / "improvement_proposals.json"))
SOP_SUMMARIES_PATH = Path(os.getenv("BILL_CORE_SOP_SUMMARIES") or (Path(__file__).resolve().parent / "workflow_sop_summaries.json"))
INTERACTIONS_PATH = Path(os.getenv("BILL_CORE_INTERACTIONS") or (Path(__file__).resolve().parent / "interactive_prompts.json"))
CONVERSATION_PREFS_PATH = Path(os.getenv("BILL_CORE_CONVERSATION_PREFS") or (Path(__file__).resolve().parent / "conversation_preferences.json"))
WORKFLOW_DRAFTS_PATH = Path(os.getenv("BILL_CORE_WORKFLOW_DRAFTS") or (Path(__file__).resolve().parent / "workflow_learning_drafts.json"))
LEARNED_PROCEDURES_PATH = Path(os.getenv("BILL_CORE_LEARNED_PROCEDURES") or (Path(__file__).resolve().parent / "learned_procedure_templates.json"))

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
    _normalize_all_proposals()
    _normalize_all_workflow_drafts()
    logger.info("Server running on: http://%s:%s", SERVER_HOST, SERVER_PORT)
    logger.info("Loaded workflows: %s from %s", len(WORKFLOW_REGISTRY), WORKFLOWS_CONFIG_PATH)
    logger.info("Loaded brain audit entries: %s", len(brain_audit_log))
    logger.info("Loaded operational memory entries: %s", len(operational_memory_log))
    logger.info("Loaded task reflections: %s", len(task_reflections))
    logger.info("Loaded improvement proposals: %s", len(improvement_proposals))
    logger.info("Loaded workflow SOP summaries: %s", len(workflow_sop_summaries))
    logger.info("Loaded interactive prompts: %s", len(interactive_prompts))
    logger.info("Loaded conversation preferences: %s", len(conversation_preferences))
    logger.info("Loaded workflow learning drafts: %s", len(workflow_learning_drafts))
    logger.info("Loaded learned procedure templates: %s", len(learned_procedure_templates))


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


def _load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(loaded, list):
            return [item for item in loaded if isinstance(item, dict)]
    except Exception as error:
        logger.error("Failed to load %s %s: %s", label, path, error)
    return []


def _save_json_list(path: Path, values: list[dict[str, Any]], max_entries: int = 2000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values[-max_entries:], indent=2), encoding="utf-8")


_loaded_learned_templates = _load_json_list(LEARNED_PROCEDURES_PATH, "learned procedure templates")
learned_procedure_templates: list[dict[str, Any]] = [
    item for item in _loaded_learned_templates if isinstance(item, dict) and str(item.get("name") or "").strip()
]
for learned_template in learned_procedure_templates:
    template_name = str(learned_template.get("name") or "").strip()
    if not template_name:
        continue
    PROCEDURE_TEMPLATES[template_name] = learned_template


WORKFLOW_REGISTRY: list[WorkflowRecord] = _load_workflow_registry()
brain_audit_log: list[dict[str, Any]] = _load_brain_audit_log()
operational_memory_log: list[dict[str, Any]] = _load_json_list(OP_MEMORY_PATH, "operational memory")
task_reflections: list[dict[str, Any]] = _load_json_list(REFLECTIONS_PATH, "task reflections")
improvement_proposals: list[dict[str, Any]] = _load_json_list(PROPOSALS_PATH, "improvement proposals")
workflow_sop_summaries: list[dict[str, Any]] = _load_json_list(SOP_SUMMARIES_PATH, "workflow SOP summaries")
interactive_prompts: list[dict[str, Any]] = _load_json_list(INTERACTIONS_PATH, "interactive prompts")
conversation_preferences: list[dict[str, Any]] = _load_json_list(CONVERSATION_PREFS_PATH, "conversation preferences")
workflow_learning_drafts: list[dict[str, Any]] = _load_json_list(WORKFLOW_DRAFTS_PATH, "workflow learning drafts")


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


def _extract_workflow_hint(command_text: str) -> str | None:
    lowered = command_text.lower()
    for record in WORKFLOW_REGISTRY:
        wf_name = str(record.workflow_name or "").strip().lower()
        if wf_name and wf_name in lowered:
            return record.workflow_name
    return _workflow_from_command(command_text)


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

    retry_count_match = re.search(r"(?:retry\s*(?:count)?|retries)\s*(?:=|to)?\s*(\d+)", command_lower)
    if retry_count_match:
        params["retry_count"] = int(retry_count_match.group(1))

    wait_match = re.search(r"(?:wait\s*(?:time)?|delay)\s*(?:=|to)?\s*(\d+)\s*(ms|milliseconds|s|sec|seconds)?", command_lower)
    if wait_match:
        amount = int(wait_match.group(1))
        units = str(wait_match.group(2) or "ms")
        params["wait_time_ms"] = amount * 1000 if units.startswith("s") and units != "ms" else amount

    selector_match = re.search(r"selector\s*strategy\s*(?:=|to)?\s*(strict|balanced|fallback)", command_lower)
    if selector_match:
        params["selector_strategy"] = selector_match.group(1)

    worker_override_match = re.search(r"worker\s*override\s*(?:=|to)?\s*([a-z0-9 _-]{2,80})", command_text, flags=re.IGNORECASE)
    if worker_override_match:
        params["worker_override"] = worker_override_match.group(1).strip()

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


def _append_operational_memory(entry: dict[str, Any]) -> None:
    operational_memory_log.append(entry)
    _save_json_list(OP_MEMORY_PATH, operational_memory_log)


def _append_task_reflection(entry: dict[str, Any]) -> None:
    task_reflections.append(entry)
    _save_json_list(REFLECTIONS_PATH, task_reflections)


def _append_improvement_proposal(entry: dict[str, Any]) -> None:
    improvement_proposals.append(entry)
    _save_json_list(PROPOSALS_PATH, improvement_proposals)


def _save_workflow_sop_summaries() -> None:
    _save_json_list(SOP_SUMMARIES_PATH, workflow_sop_summaries)


def _save_interactive_prompts() -> None:
    _save_json_list(INTERACTIONS_PATH, interactive_prompts)


def _save_conversation_preferences() -> None:
    _save_json_list(CONVERSATION_PREFS_PATH, conversation_preferences)


def _save_workflow_learning_drafts() -> None:
    _save_json_list(WORKFLOW_DRAFTS_PATH, workflow_learning_drafts)


def _save_workflow_registry() -> None:
    WORKFLOWS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = [item.model_dump() for item in WORKFLOW_REGISTRY]
    WORKFLOWS_CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _save_learned_procedure_templates() -> None:
    _save_json_list(LEARNED_PROCEDURES_PATH, learned_procedure_templates)


def _normalize_workflow_name(value: str | None) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    return base or f"learned_workflow_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"


def _extract_required_inputs_from_text(text: str) -> list[str]:
    required: list[str] = []
    patterns = [
        r"\{([a-zA-Z0-9_]+)\}",
        r"<([a-zA-Z0-9_]+)>",
        r"\b(input|parameter|field)\s*[:=]\s*([a-zA-Z0-9_]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            if len(match.groups()) == 1:
                candidate = str(match.group(1)).strip().lower()
            else:
                candidate = str(match.group(2)).strip().lower()
            if candidate and candidate not in required:
                required.append(candidate)
    return required


def _normalize_variable_input(item: Any, fallback_name: str = "input_value") -> dict[str, Any]:
    if not isinstance(item, dict):
        item = {}
    field_key = str(item.get("field_key") or fallback_name).strip() or fallback_name

    # Normalize source: accept legacy values (ask_user, environment, database) and map to
    # new canonical values: user_input | derived | constant
    raw_source = str(item.get("source") or item.get("input_source") or "user_input").strip().lower()
    source_map = {
        "ask_user": "user_input",
        "user_input": "user_input",
        "environment": "derived",
        "database": "derived",
        "derived": "derived",
        "constant": "constant",
        "fixed": "constant",
    }
    source = source_map.get(raw_source, "user_input")

    return {
        "field_key": field_key,
        "label": str(item.get("label") or field_key.replace("_", " ").title()).strip(),
        "sample_value": str(item.get("sample_value") or item.get("default_value") or "").strip(),
        "is_variable": bool(item.get("is_variable", source != "constant")),
        "required_input": bool(item.get("required_input", True)),
        # New canonical source field
        "source": source,
        # Keep legacy key for backwards compat with existing worker code
        "input_source": source,
        "source_detail": str(item.get("source_detail") or "").strip(),
        "prompt_question": str(item.get("prompt_question") or f"How should '{field_key}' be populated?").strip(),
        "example_value": str(item.get("example_value") or "").strip(),
    }


def _normalize_step(step: Any, default_order: int) -> dict[str, Any]:
    if not isinstance(step, dict):
        step = {}

    action = str(step.get("action") or "manual_step").strip() or "manual_step"
    selector = str(step.get("selector") or "").strip()
    url = str(step.get("url") or "").strip()
    instruction = str(step.get("instruction") or "").strip()
    step_name = str(step.get("step_name") or step.get("name") or f"Step {default_order}").strip() or f"Step {default_order}"

    # intent: one-sentence business-level statement of why this step exists
    intent = str(step.get("intent") or "").strip()
    if not intent:
        if action == "open_url":
            intent = "Navigate to the required starting page."
        elif action == "click_selector":
            intent = "Trigger the next workflow action."
        elif action == "type_text":
            intent = "Supply required form data."
        elif action == "select_option":
            intent = "Choose the correct option."
        elif action == "wait_for_element":
            intent = "Wait until the UI is ready to proceed."
        elif action == "page_transition":
            intent = "Confirm the workflow advanced to the next screen."
        elif action == "take_screenshot":
            intent = "Capture proof of current state."
        else:
            intent = "Complete this step as part of the workflow."

    # description: narrative of what technically happens
    description = str(step.get("description") or "").strip()
    if not description:
        description = instruction or intent

    # purpose (legacy field kept for compatibility)
    purpose = str(step.get("purpose") or "").strip()
    if not purpose:
        purpose = intent

    value = str(step.get("value") or "").strip()
    variable_inputs_raw = step.get("variable_inputs") or []
    variable_inputs = [_normalize_variable_input(item, fallback_name=f"step_{default_order}_value") for item in variable_inputs_raw if isinstance(item, dict)]
    if action == "type_text" and value and not variable_inputs:
        variable_inputs = [
            {
                "field_key": selector or f"step_{default_order}_value",
                "label": (selector or f"Step {default_order} value").replace("_", " ").title(),
                "sample_value": value,
                "is_variable": True,
                "required_input": True,
                "source": "user_input",
                "input_source": "user_input",
                "source_detail": "",
                "prompt_question": f"Is '{value}' a fixed constant, or should it be variable?",
                "example_value": value,
            }
        ]

    field_mappings = []
    raw_mappings = step.get("field_mappings") or []
    if isinstance(raw_mappings, list):
        for item in raw_mappings:
            if isinstance(item, dict):
                field_mappings.append(
                    {
                        "field": str(item.get("field") or selector or "").strip(),
                        "source": str(item.get("source") or "user_input").strip() or "user_input",
                        "source_detail": str(item.get("source_detail") or "").strip(),
                    }
                )

    if action == "type_text" and selector and not field_mappings:
        field_mappings.append({"field": selector, "source": "user_input", "source_detail": ""})

    # Validation-first: success_condition, failure_condition, recovery_strategy
    success_condition = str(step.get("success_condition") or "").strip()
    if not success_condition:
        success_condition = "The expected page or element state is reached after this step."

    failure_condition = str(step.get("failure_condition") or "").strip()
    if not failure_condition:
        if action == "click_selector":
            failure_condition = "The element is not found, not visible, or clicking it produces no change."
        elif action == "type_text":
            failure_condition = "The field does not accept input or the value is not retained."
        elif action == "wait_for_element":
            failure_condition = "The element is still absent after the timeout period."
        elif action == "open_url":
            failure_condition = "The page fails to load or loads an unexpected URL."
        else:
            failure_condition = "The expected outcome of this step is not observed."

    recovery_strategy = str(step.get("recovery_strategy") or step.get("failure_behavior") or "").strip()
    if not recovery_strategy:
        recovery_strategy = "Retry once; if still failing, pause and require human review."

    return {
        "step_order": int(step.get("step_order") or default_order),
        "name": str(step.get("name") or f"step_{default_order}"),
        "step_name": step_name,
        # Semantic meaning layer
        "intent": intent,
        "description": description,
        "purpose": purpose,
        "instruction": instruction,
        "action": action,
        "selector": selector,
        "url": url,
        "value": value,
        "option": str(step.get("option") or "").strip(),
        "manual_review_required": bool(step.get("manual_review_required", action == "manual_step")),
        "variable_inputs": variable_inputs,
        "field_mappings": field_mappings,
        "validation_rules": [str(x) for x in (step.get("validation_rules") or [])],
        # Validation-first contract
        "success_condition": success_condition,
        "failure_condition": failure_condition,
        "recovery_strategy": recovery_strategy,
        # Keep legacy field for backwards compat
        "failure_behavior": recovery_strategy,
    }


def _step_from_text_line(line: str, order: int) -> dict[str, Any]:
    stripped = line.strip().strip("-*")
    lowered = stripped.lower()
    step: dict[str, Any] = {
        "step_order": order,
        "name": f"step_{order}",
        "step_name": f"Step {order}",
        "intent": "",
        "description": stripped,
        "purpose": "",
        "instruction": stripped,
        "manual_review_required": False,
        "variable_inputs": [],
        "field_mappings": [],
        "validation_rules": [],
    }

    url_match = re.search(r"https?://\S+", stripped)
    selector_match = re.search(r"selector\s*[:=]?\s*([#\.\[\]a-zA-Z0-9_\-:'\(\)\s]+)", stripped)
    quoted_match = re.search(r"['\"]([^'\"]{2,120})['\"]", stripped)
    transition_match = re.search(r"\b(next page|continue|submit|go to|navigat(e|ion) to)\b", lowered)

    if "open" in lowered and url_match:
        step.update(
            {
                "action": "open_url",
                "url": url_match.group(0),
                "step_name": "Open Page",
                "intent": "Navigate to the required starting page.",
                "description": f"Opens the browser to {url_match.group(0)}.",
                "purpose": "Navigate to the target page.",
                "success_condition": "Target page loads and URL matches expected.",
                "failure_condition": "Page fails to load or redirects to an unexpected URL.",
                "recovery_strategy": "Retry URL load once; if still failing, stop and alert.",
                "failure_behavior": "Retry URL load, then stop and alert user.",
            }
        )
    elif "wait" in lowered:
        selector = selector_match.group(1).strip() if selector_match else "body"
        step.update(
            {
                "action": "wait_for_element",
                "selector": selector,
                "timeout_ms": 20000,
                "step_name": "Wait For Page Element",
                "intent": "Ensure the UI is ready before the next action.",
                "description": f"Waits for '{selector}' to become visible before continuing.",
                "purpose": "Ensure required UI is available before continuing.",
                "success_condition": f"'{selector}' becomes visible within the timeout.",
                "failure_condition": f"'{selector}' is still absent after timeout.",
                "recovery_strategy": "Refresh page or retry wait once; then require human intervention.",
                "failure_behavior": "Refresh or retry wait once, then require human intervention.",
            }
        )
    elif "click" in lowered:
        selector = selector_match.group(1).strip() if selector_match else (quoted_match.group(1) if quoted_match else "")
        step.update(
            {
                "action": "click_selector",
                "selector": selector,
                "step_name": "Click Control",
                "intent": "Trigger the next action in the workflow by clicking a control.",
                "description": f"Clicks the element matching '{selector}'.",
                "purpose": "Trigger the next action in the workflow.",
                "success_condition": "Expected UI state changes after click.",
                "failure_condition": "Element is not found, not clickable, or click produces no visible change.",
                "recovery_strategy": "Retry with alternate selector; if still failing, pause for review.",
                "failure_behavior": "Retry click with alternate selector, then pause for review.",
            }
        )
        if not selector:
            step["manual_review_required"] = True
    elif any(term in lowered for term in ["select", "dropdown", "choose option"]):
        selector = selector_match.group(1).strip() if selector_match else "select"
        option_value = quoted_match.group(1) if quoted_match else ""
        step.update(
            {
                "action": "select_option",
                "selector": selector,
                "option": option_value,
                "step_name": "Select Dropdown Option",
                "intent": "Choose the correct option from a dropdown to set workflow context.",
                "description": f"Selects '{option_value}' from dropdown '{selector}'.",
                "purpose": "Set dropdown value required for quoting/eligibility.",
                "success_condition": "Dropdown reflects the intended option.",
                "failure_condition": "Target option is not found in the dropdown or selection is rejected.",
                "recovery_strategy": "Retry selection; if option absent, flag for human review.",
                "failure_behavior": "Retry selection or choose fallback option, then request review.",
            }
        )
        if not option_value:
            step["manual_review_required"] = True
    elif any(term in lowered for term in ["type", "enter", "fill"]):
        selector = selector_match.group(1).strip() if selector_match else "input"
        value = quoted_match.group(1) if quoted_match else ""
        step.update(
            {
                "action": "type_text",
                "selector": selector,
                "value": value,
                "step_name": "Enter Field Value",
                "intent": "Supply required data into the form field.",
                "description": f"Types '{value}' into field '{selector}'.",
                "purpose": "Populate required input data.",
                "field_mappings": [{"field": selector, "source": "user_input", "source_detail": ""}],
                "success_condition": "Field accepts and retains the entered value.",
                "failure_condition": "Field does not accept input or value is cleared or rejected.",
                "recovery_strategy": "Retry input once; if validation error persists, request correction.",
                "failure_behavior": "Retry input once; if validation error persists, request correction.",
            }
        )
        if value:
            step["variable_inputs"] = [
                {
                    "field_key": selector,
                    "label": (selector or "field").replace("_", " ").title(),
                    "sample_value": value,
                    "is_variable": True,
                    "required_input": True,
                    "source": "user_input",
                    "input_source": "user_input",
                    "source_detail": "",
                    "prompt_question": f"Is '{value}' fixed every run, or should it be variable?",
                    "example_value": value,
                }
            ]
        if not value:
            step["manual_review_required"] = True
    elif transition_match:
        step.update(
            {
                "action": "page_transition",
                "step_name": "Move To Next Page",
                "intent": "Advance the workflow to the next screen or stage.",
                "description": "Triggers a page transition and waits for the new state to load.",
                "purpose": "Advance to the next workflow stage/page.",
                "success_condition": "URL or page title changes to the expected next stage.",
                "failure_condition": "URL does not change or an error page is shown.",
                "recovery_strategy": "Retry transition once and verify no blocking dialogs remain.",
                "failure_behavior": "Retry transition once and verify required blockers are resolved.",
            }
        )
    elif "screenshot" in lowered or "capture" in lowered:
        step.update(
            {
                "action": "take_screenshot",
                "name": f"draft_step_{order}",
                "step_name": "Capture Evidence",
                "intent": "Store visual proof of the current workflow state.",
                "description": "Takes a full-page screenshot for audit or debugging.",
                "purpose": "Store visual proof of this workflow stage.",
                "success_condition": "Screenshot file is saved.",
                "failure_condition": "Screenshot capture fails or file is not written.",
                "recovery_strategy": "Retry capture once; if still failing, log warning and continue.",
                "failure_behavior": "Retry capture once, then continue with warning.",
            }
        )
    else:
        step.update(
            {
                "action": "manual_step",
                "manual_review_required": True,
                "step_name": "Manual Review Step",
                "intent": "A human must review and define the action for this step.",
                "description": stripped or "No automatic classification possible; requires manual review.",
                "purpose": "Human interpretation needed to define the action.",
                "success_condition": "Reviewer confirms expected state is reached.",
                "failure_condition": "Reviewer is unable to determine the correct action.",
                "recovery_strategy": "Pause, collect clarification, then reclassify before continuing.",
                "failure_behavior": "Pause and collect clarification before continuing.",
            }
        )

    return _normalize_step(step, order)


def _draft_steps_from_source_text(source_text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    if not lines:
        return [
            _normalize_step(
                {
                    "step_order": 1,
                    "name": "step_1",
                    "instruction": "No source steps provided",
                    "action": "manual_step",
                    "manual_review_required": True,
                    "step_name": "Manual Review Step",
                    "purpose": "Define this step from observed behavior.",
                },
                1,
            )
        ]
    return [_step_from_text_line(line, index) for index, line in enumerate(lines, start=1)]


def _build_workflow_draft(payload: WorkflowLearningCreateRequest) -> dict[str, Any]:
    path = str(payload.learning_path or "").strip().lower()
    if path not in {"plain_english", "demonstration", "sop_checklist"}:
        raise HTTPException(status_code=400, detail="learning_path must be one of: plain_english, demonstration, sop_checklist")

    source_text = str(payload.source_text or "").strip()
    if not source_text and path != "demonstration":
        raise HTTPException(status_code=400, detail="source_text is required")

    workflow_name = _normalize_workflow_name(payload.workflow_name or "")
    goal = str(payload.goal or "").strip() or f"Execute learned workflow {workflow_name}"
    if source_text:
        steps = _draft_steps_from_source_text(source_text)
        required_inputs = _extract_required_inputs_from_text(source_text)
        requires_session = any(term in source_text.lower() for term in ["login", "session", "authenticate", "mfa"])
        description = source_text[:400]
    else:
        # Demonstration mode can begin before notes are entered.
        steps = []
        required_inputs = []
        requires_session = True
        description = "Awaiting observed demonstration capture."

    # Collect top-level variable registry from all steps (deduplicated by field_key)
    variables: list[dict[str, Any]] = []
    seen_var_keys: set[str] = set()
    for step in steps:
        for var in step.get("variable_inputs") or []:
            key = str(var.get("field_key") or "")
            if key and key not in seen_var_keys:
                seen_var_keys.add(key)
                variables.append(dict(var))

    return {
        "draft_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "learning_path": path,
        "workflow_name": workflow_name,
        "goal": goal,
        "description": description,
        "required_inputs": required_inputs,
        "required_session_state": ["authenticated_session"] if requires_session else [],
        "safe_for_unattended": not requires_session,
        "steps": steps,
        "variables": variables,
        "teaching_complete": False,
        "teaching_pending_step": 1 if steps else None,
        "validation_rules": [
            "Confirm each step has executable action",
            "Validate selectors and required values before publish",
            "Run guided test before approval",
        ],
        "fallback_strategies": [
            "Retry once with explicit selector",
            "Pause for human verification when manual review is needed",
        ],
        "common_failures": [
            "selector_not_found",
            "session_not_authenticated",
            "timeout",
        ],
        "review_status": "draft",
        "reviewer_notes": None,
        "published_workflow_name": None,
    }


def _normalize_workflow_draft(item: dict[str, Any]) -> dict[str, Any]:
    now_iso = datetime.utcnow().isoformat()
    workflow_name = _normalize_workflow_name(str(item.get("workflow_name") or ""))
    raw_steps = [dict(x) for x in (item.get("steps") or []) if isinstance(x, dict)]
    normalized_steps = [_normalize_step(step, idx) for idx, step in enumerate(raw_steps, start=1)]

    # Re-derive top-level variables from steps (preserving any already present)
    existing_vars: dict[str, dict] = {
        str(v.get("field_key") or ""): v
        for v in (item.get("variables") or [])
        if isinstance(v, dict) and v.get("field_key")
    }
    for step in normalized_steps:
        for var in step.get("variable_inputs") or []:
            key = str(var.get("field_key") or "")
            if key and key not in existing_vars:
                existing_vars[key] = dict(var)
    variables = list(existing_vars.values())

    return {
        "draft_id": str(item.get("draft_id") or item.get("id") or uuid4()),
        "created_at": str(item.get("created_at") or item.get("timestamp") or now_iso),
        "updated_at": str(item.get("updated_at") or item.get("created_at") or now_iso),
        "learning_path": str(item.get("learning_path") or "plain_english"),
        "workflow_name": workflow_name,
        "goal": str(item.get("goal") or f"Execute learned workflow {workflow_name}"),
        "description": str(item.get("description") or ""),
        "required_inputs": [str(x) for x in (item.get("required_inputs") or [])],
        "required_session_state": [str(x) for x in (item.get("required_session_state") or [])],
        "safe_for_unattended": bool(item.get("safe_for_unattended", False)),
        "steps": normalized_steps,
        "variables": variables,
        "teaching_complete": bool(item.get("teaching_complete", False)),
        "teaching_pending_step": item.get("teaching_pending_step"),
        "validation_rules": [str(x) for x in (item.get("validation_rules") or [])],
        "fallback_strategies": [str(x) for x in (item.get("fallback_strategies") or [])],
        "common_failures": [str(x) for x in (item.get("common_failures") or [])],
        "review_status": str(item.get("review_status") or "draft").strip().lower(),
        "reviewer_notes": item.get("reviewer_notes"),
        "published_workflow_name": item.get("published_workflow_name"),
    }


def _generate_step_teaching_questions(step: dict[str, Any], draft_id: str) -> TeachingSessionQuestion:
    """Generate teaching questions for a single step that still needs enrichment."""
    step_order = int(step.get("step_order") or 0)
    step_name = str(step.get("step_name") or f"Step {step_order}")
    questions: list[TeachingStepQuestion] = []

    # Q1: Confirm / correct the step intent
    questions.append(
        TeachingStepQuestion(
            step_order=step_order,
            field="intent",
            question="What does this step accomplish in the business process?",
            current_value=str(step.get("intent") or ""),
            options=[],
        )
    )

    # Q2: For each variable input, ask which source category it belongs to
    for var in step.get("variable_inputs") or []:
        key = str(var.get("field_key") or "")
        current_source = str(var.get("source") or var.get("input_source") or "user_input")
        sample = str(var.get("sample_value") or var.get("example_value") or "")
        label = str(var.get("label") or key)
        questions.append(
            TeachingStepQuestion(
                step_order=step_order,
                field=f"variable_source:{key}",
                question=(
                    f"Is the value for '{label}'{(' (e.g. ' + sample + ')') if sample else ''} "
                    "fixed every run, provided by the user at runtime, or derived from an earlier step?"
                ),
                current_value=current_source,
                options=["constant", "user_input", "derived"],
            )
        )

    # Q3: Success condition
    questions.append(
        TeachingStepQuestion(
            step_order=step_order,
            field="success_condition",
            question="What does success look like immediately after this step?",
            current_value=str(step.get("success_condition") or ""),
            options=[],
        )
    )

    # Q4: Failure condition
    questions.append(
        TeachingStepQuestion(
            step_order=step_order,
            field="failure_condition",
            question="What observable state would indicate this step failed?",
            current_value=str(step.get("failure_condition") or ""),
            options=[],
        )
    )

    return TeachingSessionQuestion(
        draft_id=draft_id,
        step_order=step_order,
        step_name=step_name,
        questions=questions,
        teaching_complete=False,
        steps_remaining=0,  # caller sets this
    )


def _apply_step_teaching_answers(
    draft: dict[str, Any],
    step_order: int,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply teaching answers to a step in the draft, then advance teaching_pending_step."""
    updated = dict(draft)
    steps = [dict(s) for s in (updated.get("steps") or [])]

    target_idx: int | None = None
    for i, s in enumerate(steps):
        if int(s.get("step_order") or 0) == step_order:
            target_idx = i
            break

    if target_idx is not None:
        step = dict(steps[target_idx])
        variable_inputs = [dict(v) for v in (step.get("variable_inputs") or [])]

        for answer in answers:
            field = str(answer.get("field") or "")
            value = str(answer.get("value") or "")

            if field.startswith("variable_source:"):
                var_key = field[len("variable_source:"):]
                for var in variable_inputs:
                    if str(var.get("field_key") or "") == var_key:
                        var["source"] = value
                        var["input_source"] = value  # legacy compat
                        break
            elif field in ("intent", "success_condition", "failure_condition", "recovery_strategy", "description"):
                step[field] = value

        step["variable_inputs"] = variable_inputs
        steps[target_idx] = step
        updated["steps"] = steps

    # Rebuild top-level variables from updated steps
    existing_vars: dict[str, dict] = {
        str(v.get("field_key") or ""): v
        for v in (updated.get("variables") or [])
        if isinstance(v, dict) and v.get("field_key")
    }
    for s in steps:
        for var in s.get("variable_inputs") or []:
            key = str(var.get("field_key") or "")
            if key:
                existing_vars[key] = dict(var)
    updated["variables"] = list(existing_vars.values())

    # Advance teaching_pending_step to next unanswered step
    all_orders = sorted(int(s.get("step_order") or 0) for s in steps)
    next_step: int | None = None
    for order in all_orders:
        if order > step_order:
            next_step = order
            break
    updated["teaching_pending_step"] = next_step
    updated["teaching_complete"] = next_step is None
    updated["updated_at"] = datetime.utcnow().isoformat()
    return updated


def _normalize_all_workflow_drafts() -> None:
    if not workflow_learning_drafts:
        return
    normalized = [_normalize_workflow_draft(item) for item in workflow_learning_drafts]
    if normalized != workflow_learning_drafts:
        workflow_learning_drafts.clear()
        workflow_learning_drafts.extend(normalized)
        _save_workflow_learning_drafts()


def _find_workflow_draft(draft_id: str) -> tuple[int, dict[str, Any]] | tuple[None, None]:
    _normalize_all_workflow_drafts()
    for idx, draft in enumerate(workflow_learning_drafts):
        if str(draft.get("draft_id") or "") == draft_id:
            return idx, draft
    return None, None


def _to_executable_browser_steps(draft_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    executable: list[dict[str, Any]] = []
    for draft_step in sorted(draft_steps, key=lambda item: int(item.get("step_order") or 0)):
        if bool(draft_step.get("manual_review_required")):
            continue
        action = str(draft_step.get("action") or "").strip()
        if action == "open_url":
            executable.append({"action": "open_url", "url": draft_step.get("url")})
        elif action == "wait_for_element":
            executable.append(
                {
                    "action": "wait_for_element",
                    "selector": draft_step.get("selector") or "body",
                    "timeout_ms": int(draft_step.get("timeout_ms") or 20000),
                }
            )
        elif action == "click_selector":
            selector = str(draft_step.get("selector") or "").strip()
            if selector:
                executable.append({"action": "click_selector", "selector": selector, "timeout_ms": 20000})
        elif action == "type_text":
            selector = str(draft_step.get("selector") or "").strip()
            if selector:
                executable.append(
                    {
                        "action": "type_text",
                        "selector": selector,
                        "value": str(draft_step.get("value") or ""),
                        "timeout_ms": 20000,
                    }
                )
        elif action == "take_screenshot":
            executable.append({"action": "take_screenshot", "name": draft_step.get("name") or "draft-capture"})

    if not executable:
        raise HTTPException(status_code=400, detail="Draft has no executable steps. Resolve manual-review steps first.")

    return executable


def _is_published_workflow(workflow_name: str | None) -> bool:
    if not workflow_name:
        return False
    needle = str(workflow_name).strip().lower()
    return any(str(item.workflow_name).strip().lower() == needle for item in WORKFLOW_REGISTRY)


def _generate_learning_proposals_for_workflow(workflow_name: str | None) -> list[dict[str, Any]]:
    if not _is_published_workflow(workflow_name):
        return []

    reflections = _search_reflections(workflow_name=workflow_name)[:120]
    if not reflections:
        return []

    success_count = sum(1 for item in reflections if str(item.get("status") or "") == "completed")
    failure_count = sum(1 for item in reflections if str(item.get("status") or "") == "failed")
    interventions = [
        item
        for item in interactive_prompts
        if str((item.get("metadata") or {}).get("workflow_name") or "").strip().lower() == str(workflow_name).strip().lower()
    ]
    proposals: list[dict[str, Any]] = []

    if success_count >= 8:
        maybe = _build_phase3_proposal(
            workflow_name=str(workflow_name),
            worker_name=None,
            proposal_type="workflow_improvement",
            title=f"Standardize successful execution path for {workflow_name}",
            description="Published workflow shows repeated successful outcomes. Consider formalizing best-path defaults.",
            supporting_evidence=[f"successful_runs={success_count}", f"failed_runs={failure_count}"],
            confidence=0.72,
            recommended_change="Promote consistent high-success parameter profile into workflow defaults.",
        )
        if maybe:
            proposals.append(maybe)

    if failure_count >= 4:
        maybe = _build_phase3_proposal(
            workflow_name=str(workflow_name),
            worker_name=None,
            proposal_type="workflow_improvement",
            title=f"Harden failure controls for {workflow_name}",
            description="Published workflow has repeated failures and may need revised validation/fallback steps.",
            supporting_evidence=[f"failed_runs={failure_count}"],
            confidence=0.74,
            recommended_change="Add stronger validation rules and fallback strategies for the repeated failure stage.",
        )
        if maybe:
            proposals.append(maybe)

    if len(interventions) >= 3:
        maybe = _build_phase3_proposal(
            workflow_name=str(workflow_name),
            worker_name=None,
            proposal_type="workflow_improvement",
            title=f"Reduce human interventions for {workflow_name}",
            description="Frequent guided/interactive interventions indicate automation gaps in published workflow.",
            supporting_evidence=[f"intervention_count={len(interventions)}"],
            confidence=0.7,
            recommended_change="Refine workflow steps to reduce manual checkpoints while preserving safety gates.",
        )
        if maybe:
            proposals.append(maybe)

    return proposals


def _append_interactive_prompt(entry: dict[str, Any]) -> None:
    interactive_prompts.append(entry)
    _save_interactive_prompts()


def _find_interaction(interaction_id: str) -> dict[str, Any] | None:
    for item in interactive_prompts:
        if str(item.get("interaction_id") or "") == interaction_id:
            return item
    return None


def _create_interaction_prompt(
    interaction_type: str,
    command: str,
    recommendation: str,
    questions: list[str],
    pending_adjustments: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "interaction_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "interaction_type": interaction_type,
        "command": command,
        "workflow_name": (metadata or {}).get("workflow_name"),
        "task_id": (metadata or {}).get("task_id"),
        "status": "pending",
        "recommendation": recommendation,
        "questions": list(questions or []),
        "pending_adjustments": dict(pending_adjustments or {}),
        "metadata": dict(metadata or {}),
    }
    _append_interactive_prompt(entry)
    return entry


def _set_conversation_preference(key: str, value: Any) -> dict[str, Any]:
    now_iso = datetime.utcnow().isoformat()
    for idx, item in enumerate(conversation_preferences):
        if str(item.get("key") or "") == key:
            updated = {"key": key, "value": value, "updated_at": now_iso}
            conversation_preferences[idx] = updated
            _save_conversation_preferences()
            return updated

    created = {"key": key, "value": value, "updated_at": now_iso}
    conversation_preferences.append(created)
    _save_conversation_preferences()
    return created


def _get_conversation_preference(key: str) -> Any:
    for item in reversed(conversation_preferences):
        if str(item.get("key") or "") == key:
            return item.get("value")
    return None


def _parse_conversation_preference_updates(command_text: str) -> list[dict[str, Any]]:
    lowered = command_text.lower()
    updates: list[dict[str, Any]] = []

    prefer_worker = re.search(r"(?:prefer|default to|use)\s+worker\s+([A-Za-z0-9 _-]{2,80})", command_text, flags=re.IGNORECASE)
    if prefer_worker:
        updates.append({"key": "preferred_worker", "value": prefer_worker.group(1).strip()})

    retries_match = re.search(r"(?:default|set)\s+retr(?:y|ies)\s*(?:to)?\s*(\d+)", lowered)
    if retries_match:
        updates.append({"key": "execution.retry_count", "value": int(retries_match.group(1))})

    wait_match = re.search(r"(?:default|set)\s+wait(?:\s*time)?\s*(?:to)?\s*(\d+)\s*(ms|seconds?|sec|s)?", lowered)
    if wait_match:
        amount = int(wait_match.group(1))
        units = str(wait_match.group(2) or "ms")
        wait_ms = amount * 1000 if units.startswith("s") and units != "ms" else amount
        updates.append({"key": "execution.wait_time_ms", "value": wait_ms})

    selector_match = re.search(r"selector strategy\s*(?:to|=)?\s*(strict|balanced|fallback)", lowered)
    if selector_match:
        updates.append({"key": "execution.selector_strategy", "value": selector_match.group(1)})

    workflow_pages = re.search(r"workflow\s+([a-z0-9_-]+)\s+max\s+pages?\s*(?:to|=)?\s*(\d+)", lowered)
    if workflow_pages:
        updates.append(
            {
                "key": f"workflow_constraint:{workflow_pages.group(1)}",
                "value": {"max_pages": int(workflow_pages.group(2))},
            }
        )

    return updates


def _apply_conversation_preferences(
    workflow_name: str | None,
    params: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    adjusted = dict(params)
    reasoning: list[str] = []

    retry_count = _get_conversation_preference("execution.retry_count")
    if isinstance(retry_count, int) and retry_count > 0 and "retry_count" not in adjusted:
        adjusted["retry_count"] = retry_count
        reasoning.append("Applied conversation preference: retry_count.")

    wait_time_ms = _get_conversation_preference("execution.wait_time_ms")
    if isinstance(wait_time_ms, int) and wait_time_ms > 0 and "wait_time_ms" not in adjusted:
        adjusted["wait_time_ms"] = wait_time_ms
        reasoning.append("Applied conversation preference: wait_time_ms.")

    selector_strategy = _get_conversation_preference("execution.selector_strategy")
    if isinstance(selector_strategy, str) and selector_strategy and "selector_strategy" not in adjusted:
        adjusted["selector_strategy"] = selector_strategy
        reasoning.append("Applied conversation preference: selector strategy.")

    if workflow_name:
        wf_pref = _get_conversation_preference(f"workflow_constraint:{workflow_name}")
        if isinstance(wf_pref, dict):
            for key, value in wf_pref.items():
                adjusted.setdefault(key, value)
            if wf_pref:
                reasoning.append(f"Applied workflow constraints for {workflow_name}.")

    return adjusted, reasoning


def _recommended_change_to_adjustments(recommended_change: str) -> dict[str, Any]:
    lowered = str(recommended_change or "").lower()
    adjustments: dict[str, Any] = {}

    retry_match = re.search(r"retry\s*(?:count)?\s*(?:to|=)?\s*(\d+)", lowered)
    if retry_match:
        adjustments["retry_count"] = int(retry_match.group(1))

    timeout_match = re.search(r"timeout\s*(?:to|=)?\s*(\d+)", lowered)
    if timeout_match:
        adjustments["page_timeout_ms"] = int(timeout_match.group(1))

    if "strict" in lowered and "selector" in lowered:
        adjustments["strict_selectors_only"] = True

    if "session" in lowered or "login" in lowered:
        adjustments["require_session_ready"] = True

    return adjustments


def _has_non_trivial_adjustments(adjustments: dict[str, Any]) -> bool:
    if not adjustments:
        return False
    sensitive_keys = {
        "retry_count",
        "wait_time_ms",
        "selector_strategy",
        "worker_override",
        "target_machine_uuid",
        "strict_selectors_only",
        "page_timeout_ms",
        "require_session_ready",
        "network_stability_check",
    }
    return any(key in sensitive_keys for key in adjustments.keys())


def _task_by_id(task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    for task in tasks:
        if str(task.get("id") or "") == task_id:
            return task
    return None


def _attach_live_reasoning(task_id: str | None, reasoning_steps: list[str]) -> None:
    task = _task_by_id(task_id)
    if not task:
        return
    for step in reasoning_steps:
        _append_task_log(task, f"Reasoning: {step}")


def _create_failure_interaction_if_needed(task: dict[str, Any], reflection: dict[str, Any]) -> None:
    workflow_name = str(reflection.get("workflow_name") or "").strip() or None
    recent_failed = _search_reflections(workflow_name=workflow_name, status="failed")[:5]
    if len(recent_failed) < 2:
        return

    recommendation = str(reflection.get("recommended_next_action") or "Review worker/session before retry.")
    pending_adjustments: dict[str, Any] = {}
    retry_strategy = str(reflection.get("retry_strategy") or "")
    if "higher timeout" in retry_strategy.lower():
        pending_adjustments["page_timeout_ms"] = 60000
    if "reduced scope" in retry_strategy.lower():
        pending_adjustments.setdefault("max_pages", 3)

    _create_interaction_prompt(
        interaction_type="troubleshooting_confirmation",
        command=f"failure:{task.get('id')}",
        recommendation=recommendation,
        questions=[
            "Approve retry with suggested adjustments?",
            "Do you want to override worker selection?",
        ],
        pending_adjustments=pending_adjustments,
        metadata={
            "workflow_name": workflow_name,
            "source_task_id": task.get("id"),
            "selected_worker_name": reflection.get("alternative_worker"),
        },
    )


def _record_operational_memory(kind: str, summary: str, details: dict[str, Any] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    entry = {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "kind": kind,
        "summary": summary,
        "details": details or {},
        "tags": tags or [],
    }
    _append_operational_memory(entry)
    return entry


def _extract_failure_category(error_text: str | None) -> str:
    lowered = str(error_text or "").lower()
    if not lowered:
        return "unknown"
    if any(term in lowered for term in ["timeout", "timed out", "time out"]):
        return "timeout"
    if any(term in lowered for term in ["selector", "element", "not found", "no such"]):
        return "selector"
    if any(term in lowered for term in ["login", "session", "unauthorized", "forbidden", "401", "403"]):
        return "session/login"
    if any(term in lowered for term in ["network", "dns", "connection", "refused", "reset"]):
        return "network"
    return "unknown"


def _classification_default_fix(classification: str) -> str:
    if classification == "timeout":
        return "Increase timeout and reduce workload size for retry."
    if classification == "selector":
        return "Validate selectors against current page structure before rerun."
    if classification == "session/login":
        return "Re-authenticate worker session before executing workflow."
    if classification == "network":
        return "Verify worker connectivity and destination availability."
    return "Inspect worker logs for latest stack trace and environment state."


def _classification_retry_strategy(classification: str) -> str:
    if classification == "timeout":
        return "Retry with higher timeout and lower scope (fewer pages/clients)."
    if classification == "selector":
        return "Retry in strict mode after selector validation."
    if classification == "session/login":
        return "Retry only after confirming logged-in authenticated session."
    if classification == "network":
        return "Retry after network check with one controlled attempt."
    return "Retry once with focused scope and inspect logs if failure repeats."


def _workflow_reflection_window(workflow_name: str | None, limit: int = 60) -> list[dict[str, Any]]:
    records = _search_reflections(workflow_name=workflow_name)
    return records[: max(1, min(limit, 200))]


def _workflow_worker_scores(workflow_name: str | None) -> dict[str, dict[str, Any]]:
    reflections = _workflow_reflection_window(workflow_name, limit=200)
    now = datetime.utcnow()
    scores: dict[str, dict[str, Any]] = {}

    for item in reflections:
        worker = str(item.get("worker_name") or "unknown")
        bucket = scores.setdefault(worker, {"total": 0, "success": 0, "recent_failures": 0, "score": 0.0})
        bucket["total"] += 1
        status = str(item.get("status") or "").lower()
        if status == "completed":
            bucket["success"] += 1
        elif status == "failed":
            finished_at = str(item.get("finished_at") or item.get("timestamp") or "")
            try:
                if finished_at and (now - datetime.fromisoformat(finished_at)).total_seconds() <= 86400:
                    bucket["recent_failures"] += 1
            except ValueError:
                bucket["recent_failures"] += 1

    for worker, bucket in scores.items():
        total = max(1, int(bucket.get("total") or 1))
        success_rate = (bucket.get("success", 0) / total) * 100.0
        recent_failure_penalty = float(bucket.get("recent_failures", 0)) * 12.0
        sample_bonus = min(total, 12) * 1.2
        bucket["success_rate"] = round(success_rate, 1)
        bucket["score"] = round(success_rate + sample_bonus - recent_failure_penalty, 2)

    return scores


def _memory_ranked_workers(machines: list[MachineRecord], workflow_name: str | None) -> list[tuple[MachineRecord, dict[str, Any]]]:
    worker_scores = _workflow_worker_scores(workflow_name)
    ranked: list[tuple[MachineRecord, dict[str, Any]]] = []
    for machine in machines:
        stats = worker_scores.get(
            str(machine.machine_name or ""),
            {"total": 0, "success": 0, "recent_failures": 0, "success_rate": 0.0, "score": 0.0},
        )
        ranked.append((machine, stats))

    ranked.sort(
        key=lambda pair: (
            0 if pair[0].online else 1,
            0 if _worker_is_idle(pair[0]) else 1,
            -float(pair[1].get("score") or 0.0),
            pair[0].machine_name or "",
        )
    )
    return ranked


def _select_best_worker_with_memory(
    machines: list[MachineRecord],
    workflow_name: str | None,
    preferred_uuid: str | None = None,
) -> tuple[MachineRecord | None, str, list[str]]:
    warnings: list[str] = []

    preferred = _find_worker_by_hint(machines, preferred_uuid)
    if preferred and preferred.online:
        return preferred, "Used explicitly requested worker target.", warnings

    ranked = _memory_ranked_workers(machines, workflow_name)
    if not ranked:
        return None, "No worker candidates were available.", warnings

    best_machine, stats = ranked[0]
    reasoning = (
        f"Selected {best_machine.machine_name} using memory score={stats.get('score', 0)} "
        f"success_rate={stats.get('success_rate', 0)}% recent_failures={stats.get('recent_failures', 0)}."
    )
    return best_machine, reasoning, warnings


def _preflight_memory_warnings(workflow_name: str | None, selected_worker: MachineRecord | None) -> list[str]:
    warnings: list[str] = []
    recent = _workflow_reflection_window(workflow_name, limit=8)
    recent_failed = [item for item in recent if str(item.get("status") or "").lower() == "failed"]

    if len(recent_failed) >= 2:
        warnings.append(f"Recent runs show repeated failures ({len(recent_failed)} in latest window).")

    if any(str(item.get("failure_classification") or "") == "session/login" for item in recent_failed):
        warnings.append("Session/login issues were recently observed; confirm authentication state before run.")

    if selected_worker:
        worker_failed = [
            item
            for item in recent_failed
            if str(item.get("worker_name") or "").lower() == str(selected_worker.machine_name or "").lower()
        ]
        if worker_failed:
            warnings.append(
                f"Selected worker {selected_worker.machine_name} has prior failures for this workflow in recent history."
            )

    return warnings


def _find_reflection_by_task_id(task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    matches = [item for item in _search_reflections() if str(item.get("task_id") or "") == str(task_id)]
    return matches[0] if matches else None


def _latest_worker_selection_audit() -> dict[str, Any] | None:
    for item in reversed(brain_audit_log):
        if str(item.get("interpreted_intent") or "") == "known_workflow" and item.get("selected_worker"):
            return item
    return None


def _alternative_worker_for_workflow(workflow_name: str | None, failed_worker_name: str | None) -> str | None:
    ranked = _memory_ranked_workers(list_machines(), workflow_name)
    for machine, _stats in ranked:
        if not machine.online:
            continue
        if failed_worker_name and str(machine.machine_name or "").lower() == str(failed_worker_name).lower():
            continue
        return machine.machine_name
    return None


def _memory_adjust_workflow_parameters(workflow_name: str | None, params: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    adjusted = dict(params)
    reasoning: list[str] = []
    recent_failed = _search_reflections(workflow_name=workflow_name, status="failed")[:8]
    if not recent_failed:
        return adjusted, reasoning

    classes: dict[str, int] = {}
    for item in recent_failed:
        cls = str(item.get("failure_classification") or "unknown")
        classes[cls] = classes.get(cls, 0) + 1

    top_class = sorted(classes.items(), key=lambda pair: pair[1], reverse=True)[0][0]
    if top_class == "timeout":
        adjusted.setdefault("page_timeout_ms", 60000)
        if "max_pages" not in adjusted:
            adjusted["max_pages"] = 3
        reasoning.append("Adjusted timeout/page scope due to recent timeout failures.")
    elif top_class == "selector":
        adjusted.setdefault("strict_selectors_only", True)
        adjusted.setdefault("retry_failed_only", True)
        reasoning.append("Enabled strict selector-safe retry due to selector-related failures.")
    elif top_class == "session/login":
        adjusted.setdefault("require_session_ready", True)
        reasoning.append("Added session readiness guard due to recent login/session failures.")
    elif top_class == "network":
        adjusted.setdefault("retry_failed_only", True)
        adjusted.setdefault("network_stability_check", True)
        reasoning.append("Enabled network-stability retry mode due to recent connectivity failures.")

    return adjusted, reasoning


def _extract_failure_stage(error_text: str | None, logs: list[dict[str, Any]] | None = None) -> str | None:
    lowered = str(error_text or "").lower()
    if any(term in lowered for term in ["login", "session", "unauthorized", "forbidden", "401", "403"]):
        return "authentication"
    if any(term in lowered for term in ["selector", "element", "not found", "no such"]):
        return "ui_interaction"
    if any(term in lowered for term in ["timeout", "timed out", "time out"]):
        return "timing"
    if any(term in lowered for term in ["network", "dns", "connection", "refused", "reset"]):
        return "connectivity"
    if logs:
        for log_item in reversed(logs[-8:]):
            message = str(log_item.get("message") or "").lower()
            if "assigned" in message:
                return "execution"
    return None


def _worker_name_from_uuid(machine_uuid: str | None) -> str | None:
    if not machine_uuid:
        return None
    with _workers_lock:
        worker = registered_workers.get(machine_uuid)
        if worker is not None:
            return worker.get("machine_name") or machine_uuid
    return machine_uuid


def _normalize_reflection_record(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status") or item.get("outcome") or "unknown").lower()
    if status == "success":
        status = "completed"
    elif status == "failure":
        status = "failed"

    worker_name = item.get("worker_name")
    if not worker_name:
        worker_name = _worker_name_from_uuid(item.get("machine_uuid"))

    supporting_evidence = str(item.get("supporting_evidence") or item.get("evidence") or "")
    recommended_next_action = str(item.get("recommended_next_action") or item.get("next_action") or "")
    likely_root_cause = str(item.get("likely_root_cause") or item.get("root_cause") or "unknown")

    normalized = {
        "id": str(item.get("id") or uuid4()),
        "timestamp": str(item.get("timestamp") or datetime.utcnow().isoformat()),
        "task_id": str(item.get("task_id") or ""),
        "workflow_name": item.get("workflow_name") or item.get("task_type"),
        "worker_name": worker_name,
        "started_at": item.get("started_at") or item.get("created_at"),
        "finished_at": item.get("finished_at") or item.get("completed_at"),
        "status": status,
        "failure_stage": item.get("failure_stage"),
        "failure_classification": item.get("failure_classification") or _extract_failure_category(
            str(item.get("supporting_evidence") or item.get("evidence") or "")
        ),
        "likely_root_cause": likely_root_cause,
        "supporting_evidence": supporting_evidence,
        "recommended_next_action": recommended_next_action,
        "retry_strategy": item.get("retry_strategy"),
        "alternative_worker": item.get("alternative_worker"),
        "potential_fix": item.get("potential_fix"),
        "recommendation_feedback": [str(x) for x in (item.get("recommendation_feedback") or [])],
        "confidence": float(item.get("confidence") or 0.5),
    }
    return normalized


def _normalize_proposal_record(item: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(item.get("proposal_id") or item.get("id") or uuid4())
    created_at = str(item.get("created_at") or item.get("timestamp") or datetime.utcnow().isoformat())
    workflow_name = str(item.get("workflow_name") or "unknown_workflow")
    title = str(item.get("title") or "Untitled proposal")
    description = str(item.get("description") or item.get("rationale") or "")
    supporting_evidence = item.get("supporting_evidence") or item.get("evidence") or []
    if not isinstance(supporting_evidence, list):
        supporting_evidence = [str(supporting_evidence)]
    recommended_change = str(item.get("recommended_change") or " | ".join(item.get("suggested_changes") or []) or "Review recommendation")

    normalized = {
        "proposal_id": proposal_id,
        "created_at": created_at,
        "workflow_name": workflow_name,
        "worker_name": item.get("worker_name"),
        "proposal_type": str(item.get("proposal_type") or "workflow_adjustment"),
        "title": title,
        "description": description,
        "supporting_evidence": [str(x) for x in supporting_evidence],
        "confidence": float(item.get("confidence") or 0.5),
        "recommended_change": recommended_change,
        "status": str(item.get("status") or "open"),
        "feedback": [str(x) for x in (item.get("feedback") or [])],
    }
    return normalized


def _normalize_all_proposals() -> None:
    global improvement_proposals
    improvement_proposals = [_normalize_proposal_record(item) for item in improvement_proposals]


def _proposal_duplicate_exists(workflow_name: str, proposal_type: str, title: str) -> bool:
    wf = workflow_name.strip().lower()
    pt = proposal_type.strip().lower()
    tt = title.strip().lower()
    for item in improvement_proposals:
        normalized = _normalize_proposal_record(item)
        if str(normalized.get("workflow_name") or "").strip().lower() != wf:
            continue
        if str(normalized.get("proposal_type") or "").strip().lower() != pt:
            continue
        if str(normalized.get("title") or "").strip().lower() != tt:
            continue
        if str(normalized.get("status") or "open").lower() in {"open", "approved", "deferred"}:
            return True
    return False


def _create_proposal(
    workflow_name: str,
    proposal_type: str,
    title: str,
    description: str,
    supporting_evidence: list[str],
    recommended_change: str,
    confidence: float,
    worker_name: str | None = None,
) -> dict[str, Any] | None:
    if _proposal_duplicate_exists(workflow_name, proposal_type, title):
        return None

    proposal = {
        "proposal_id": str(uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "workflow_name": workflow_name,
        "worker_name": worker_name,
        "proposal_type": proposal_type,
        "title": title,
        "description": description,
        "supporting_evidence": supporting_evidence,
        "confidence": max(0.0, min(confidence, 1.0)),
        "recommended_change": recommended_change,
        "status": "open",
        "feedback": [],
    }
    return proposal


def _generate_phase3_proposals_for_workflow(workflow_name: str | None) -> list[dict[str, Any]]:
    if not workflow_name:
        return []

    generated: list[dict[str, Any]] = []
    reflections = _search_reflections(workflow_name=workflow_name)[:120]
    if not reflections:
        return []

    failures = [r for r in reflections if str(r.get("status") or "").lower() == "failed"]
    successes = [r for r in reflections if str(r.get("status") or "").lower() == "completed"]

    failure_class_counts: dict[str, int] = {}
    for item in failures:
        cls = str(item.get("failure_classification") or "unknown")
        failure_class_counts[cls] = failure_class_counts.get(cls, 0) + 1

    for cls, count in failure_class_counts.items():
        if count >= 3:
            ptype = "workflow_adjustment"
            if cls == "selector":
                ptype = "selector_fix_suggestion"
            elif cls in {"timeout", "network"}:
                ptype = "retry_logic_change"
            elif cls == "session/login":
                ptype = "session/login_prerequisite_warning"
            proposal = _create_proposal(
                workflow_name=workflow_name,
                proposal_type=ptype,
                title=f"Reduce repeated {cls} failures in {workflow_name}",
                description=f"The same failure class ({cls}) repeated {count} times.",
                supporting_evidence=[f"failure_class={cls}", f"count={count}"],
                recommended_change=f"Add/strengthen {cls} guardrails and preflight checks for {workflow_name}.",
                confidence=0.78,
            )
            if proposal:
                generated.append(proposal)

            if cls in {"timeout", "network"}:
                retry_proposal = _create_proposal(
                    workflow_name=workflow_name,
                    proposal_type="retry_logic_change",
                    title=f"Tune retry logic for {cls} instability in {workflow_name}",
                    description=f"Repeated {cls} failures indicate current retry strategy is insufficient.",
                    supporting_evidence=[f"failure_class={cls}", f"count={count}"],
                    recommended_change="Adopt bounded backoff retries with stage-specific guardrails.",
                    confidence=0.76,
                )
                if retry_proposal:
                    generated.append(retry_proposal)

    workaround_counts: dict[str, int] = {}
    for item in successes:
        action = str(item.get("recommended_next_action") or "").strip()
        if action:
            workaround_counts[action] = workaround_counts.get(action, 0) + 1
    for action, count in workaround_counts.items():
        if count >= 3:
            proposal = _create_proposal(
                workflow_name=workflow_name,
                proposal_type="SOP_update_suggestion",
                title=f"Promote repeated workaround to SOP for {workflow_name}",
                description="The same workaround pattern repeatedly succeeded.",
                supporting_evidence=[f"workaround={action}", f"success_count={count}"],
                recommended_change=f"Document this as a standard fix: {action}",
                confidence=0.74,
            )
            if proposal:
                generated.append(proposal)

    chronological = sorted(reflections, key=lambda item: str(item.get("finished_at") or item.get("timestamp") or ""))
    repeated_recoveries = 0
    for idx in range(1, len(chronological)):
        prev_status = str(chronological[idx - 1].get("status") or "").lower()
        current_status = str(chronological[idx].get("status") or "").lower()
        if prev_status == "failed" and current_status == "completed":
            repeated_recoveries += 1
    if repeated_recoveries >= 3:
        proposal = _create_proposal(
            workflow_name=workflow_name,
            proposal_type="workflow_adjustment",
            title=f"Codify recovery pattern for {workflow_name}",
            description="Repeated fail-then-success recoveries suggest a stable corrective sequence exists.",
            supporting_evidence=[f"recovery_transitions={repeated_recoveries}"],
            recommended_change="Capture the recovery sequence as standard pre-checks and fallback flow.",
            confidence=0.75,
        )
        if proposal:
            generated.append(proposal)

    worker_scores = _workflow_worker_scores(workflow_name)
    ranked = sorted(worker_scores.items(), key=lambda pair: float(pair[1].get("score") or 0.0), reverse=True)
    if len(ranked) >= 2:
        top_name, top_stats = ranked[0]
        second_name, second_stats = ranked[1]
        top_rate = float(top_stats.get("success_rate") or 0.0)
        second_rate = float(second_stats.get("success_rate") or 0.0)
        if top_rate >= second_rate + 20 and int(top_stats.get("total") or 0) >= 4:
            proposal = _create_proposal(
                workflow_name=workflow_name,
                worker_name=top_name,
                proposal_type="worker_preference_suggestion",
                title=f"Prefer {top_name} for {workflow_name}",
                description="One worker consistently outperforms alternatives.",
                supporting_evidence=[
                    f"{top_name}_success_rate={top_rate}",
                    f"{second_name}_success_rate={second_rate}",
                ],
                recommended_change=f"Prefer worker {top_name} by default for {workflow_name}.",
                confidence=0.81,
            )
            if proposal:
                generated.append(proposal)

    session_interventions = sum(1 for item in failures if str(item.get("failure_classification") or "") == "session/login")
    if session_interventions >= 2:
        proposal = _create_proposal(
            workflow_name=workflow_name,
            proposal_type="session/login_prerequisite_warning",
            title=f"Add explicit session prerequisite for {workflow_name}",
            description="Human intervention for login/session appears repeatedly required.",
            supporting_evidence=[f"session_login_failures={session_interventions}"],
            recommended_change="Add a hard pre-run session checklist and login verification step.",
            confidence=0.8,
        )
        if proposal:
            generated.append(proposal)

    return generated


def _update_sop_summary_for_workflow(workflow_name: str | None) -> dict[str, Any] | None:
    if not workflow_name:
        return None

    reflections = _search_reflections(workflow_name=workflow_name)[:150]
    if not reflections:
        return None

    workflow_record = next((wf for wf in WORKFLOW_REGISTRY if wf.workflow_name == workflow_name), None)
    purpose = (workflow_record.description if workflow_record else f"Operational execution of {workflow_name}") or f"Operational execution of {workflow_name}"

    prerequisites: list[str] = []
    if workflow_record and workflow_record.login_or_session_required:
        prerequisites.append("Authenticated session must be active before run")
    if any(str(item.get("failure_classification") or "") == "session/login" for item in reflections):
        prerequisites.append("Verify login/session readiness (historical session issues detected)")

    normal_flow = [
        "Select preferred online worker",
        "Run workflow with memory-aware parameters",
        "Monitor logs and completion status",
    ]

    common_failures_counts: dict[str, int] = {}
    for item in reflections:
        if str(item.get("status") or "") != "failed":
            continue
        cls = str(item.get("failure_classification") or "unknown")
        common_failures_counts[cls] = common_failures_counts.get(cls, 0) + 1
    common_failures = [f"{k}: {v} occurrences" for k, v in sorted(common_failures_counts.items(), key=lambda pair: pair[1], reverse=True)[:5]]

    fix_counts: dict[str, int] = {}
    for item in reflections:
        action = str(item.get("recommended_next_action") or "").strip()
        if action:
            fix_counts[action] = fix_counts.get(action, 0) + 1
    recommended_fixes = [
        f"{k} (seen {v} times)" for k, v in sorted(fix_counts.items(), key=lambda pair: pair[1], reverse=True)[:5]
    ]

    worker_scores = _workflow_worker_scores(workflow_name)
    best_worker_patterns = [
        f"{worker}: success_rate={stats.get('success_rate', 0)}% total={stats.get('total', 0)} recent_failures={stats.get('recent_failures', 0)}"
        for worker, stats in sorted(worker_scores.items(), key=lambda pair: float(pair[1].get("score") or 0.0), reverse=True)[:5]
    ]

    summary = {
        "workflow_name": workflow_name,
        "purpose": purpose,
        "prerequisites": list(dict.fromkeys(prerequisites)),
        "normal_flow": normal_flow,
        "common_failures": common_failures,
        "recommended_fixes": recommended_fixes,
        "best_worker_patterns": best_worker_patterns,
        "updated_at": datetime.utcnow().isoformat(),
    }

    existing_idx = next((idx for idx, item in enumerate(workflow_sop_summaries) if str(item.get("workflow_name")) == workflow_name), None)
    if existing_idx is None:
        workflow_sop_summaries.append(summary)
    else:
        workflow_sop_summaries[existing_idx] = summary
    _save_workflow_sop_summaries()
    return summary


def _run_phase3_adaptive_analysis(workflow_name: str | None) -> list[dict[str, Any]]:
    proposals = _generate_phase3_proposals_for_workflow(workflow_name)
    proposals.extend(_generate_learning_proposals_for_workflow(workflow_name))
    for proposal in proposals:
        _append_improvement_proposal(_normalize_proposal_record(proposal))
    if proposals:
        _record_operational_memory(
            "adaptive_proposals_generated",
            f"Generated {len(proposals)} adaptive proposal(s) for workflow={workflow_name}",
            details={"workflow_name": workflow_name, "proposal_ids": [item.get("proposal_id") for item in proposals]},
            tags=["phase3", "proposal", "review_required"],
        )
    _update_sop_summary_for_workflow(workflow_name)
    return proposals


def _search_reflections(
    workflow_name: str | None = None,
    worker_name: str | None = None,
    status: str | None = None,
    date: str | None = None,
    keywords: str | None = None,
) -> list[dict[str, Any]]:
    records = [_normalize_reflection_record(item) for item in task_reflections]

    if workflow_name:
        wf = workflow_name.strip().lower()
        records = [item for item in records if str(item.get("workflow_name") or "").lower() == wf]

    if worker_name:
        wn = worker_name.strip().lower()
        records = [item for item in records if str(item.get("worker_name") or "").lower() == wn]

    if status:
        st = status.strip().lower()
        records = [item for item in records if str(item.get("status") or "").lower() == st]

    if date:
        target = date.strip()
        records = [
            item
            for item in records
            if str(item.get("started_at") or item.get("finished_at") or item.get("timestamp") or "").startswith(target)
        ]

    if keywords:
        terms = [part.strip().lower() for part in re.split(r"[,\s]+", keywords) if part.strip()]
        if terms:
            def _text_blob(entry: dict[str, Any]) -> str:
                return " ".join(
                    [
                        str(entry.get("workflow_name") or ""),
                        str(entry.get("worker_name") or ""),
                        str(entry.get("status") or ""),
                        str(entry.get("failure_stage") or ""),
                        str(entry.get("likely_root_cause") or ""),
                        str(entry.get("supporting_evidence") or ""),
                        str(entry.get("recommended_next_action") or ""),
                    ]
                ).lower()

            records = [item for item in records if all(term in _text_blob(item) for term in terms)]

    return sorted(records, key=lambda item: str(item.get("timestamp") or ""), reverse=True)


def _build_task_reflection(task: dict, outcome: str, machine_uuid: str | None = None, error_text: str | None = None) -> dict[str, Any]:
    payload = task.get("payload") or {}
    task_type = payload.get("task_type")
    workflow_name = payload.get("workflow_name") or task_type
    status = "completed" if outcome == "success" else "failed"
    failure_classification = classify_error(error_text) if status == "failed" else None
    failure_stage = _extract_failure_stage(error_text, logs=task.get("logs") or []) if status == "failed" else None
    worker_name = _worker_name_from_uuid(machine_uuid or task.get("assigned_machine_uuid"))
    evidence = "Task completed with result payload." if status == "completed" else f"Task failed with error: {error_text or 'unknown'}"

    if outcome == "success":
        root_cause = "Execution path was valid for the selected workflow and environment."
        next_action = "Use this run configuration as a baseline and monitor for regressions."
        confidence = 0.8
    else:
        failure_category = failure_classification or "unknown"
        root_cause = f"Most likely failure category: {failure_category}."
        if failure_category == "timeout":
            next_action = "Increase timeout or reduce page workload, then retry on an idle worker."
        elif failure_category == "selector_issue":
            next_action = "Validate selectors against current UI structure before retrying."
        elif failure_category == "session_login":
            next_action = "Confirm worker session/login state, then retry the workflow."
        elif failure_category == "network":
            next_action = "Check network connectivity for the worker and destination endpoint."
        elif failure_category == "pagination_issue":
            next_action = "Close any open dialogs on the worker screen and retry."
        else:
            next_action = "Inspect worker logs for stack trace details and retry with tighter scope."
        confidence = score_confidence(failure_category, error_text)

    # Build human-readable explanation with memory hint
    similar = (
        find_similar_failure(
            task_reflections,
            category=failure_classification or "unknown",
            workflow_name=workflow_name,
            current_task_id=task.get("id"),
        )
        if status == "failed"
        else None
    )
    human_explanation = (
        generate_explanation(failure_classification or "unknown", error_text=error_text, similar_failure=similar)
        if status == "failed"
        else None
    )
    human_summary = build_human_summary(
        failure_classification or "unknown", workflow_name, worker_name, status
    )

    reflection = {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "task_id": task.get("id"),
        "workflow_name": workflow_name,
        "worker_name": worker_name,
        "started_at": task.get("created_at"),
        "finished_at": task.get("completed_at") or datetime.utcnow().isoformat(),
        "status": status,
        "failure_stage": failure_stage,
        "failure_classification": failure_classification,
        "likely_root_cause": root_cause,
        "supporting_evidence": evidence,
        "recommended_next_action": next_action,
        "retry_strategy": _classification_retry_strategy(failure_classification or "unknown") if status == "failed" else None,
        "alternative_worker": _alternative_worker_for_workflow(workflow_name, worker_name) if status == "failed" else None,
        "potential_fix": _classification_default_fix(failure_classification or "unknown") if status == "failed" else None,
        "confidence": confidence,
        "human_summary": human_summary,
        "human_explanation": human_explanation,
    }
    return reflection


def _proposal_exists_with_title(title: str) -> bool:
    needle = title.strip().lower()
    return any(str(item.get("title") or "").strip().lower() == needle for item in improvement_proposals)


def _generate_improvement_proposal_from_reflection(reflection: dict[str, Any]) -> dict[str, Any] | None:
    normalized = _normalize_reflection_record(reflection)
    if normalized.get("status") != "failed":
        return None

    evidence = normalized.get("supporting_evidence") or ""
    category = _extract_failure_category(evidence)
    recent_same_category = [
        _normalize_reflection_record(item)
        for item in task_reflections[-50:]
        if _normalize_reflection_record(item).get("status") == "failed"
        and _extract_failure_category(_normalize_reflection_record(item).get("supporting_evidence")) == category
    ]
    if len(recent_same_category) < 2:
        return None

    title = f"Proposal: reduce repeated {category} failures"
    if _proposal_exists_with_title(title):
        return None

    suggested_changes = [
        "Add preflight checks before task start to detect likely failure conditions.",
        "Capture richer failure diagnostics from worker logs and attach to task record.",
        "Introduce a safe retry strategy with bounded attempts and explicit operator approval.",
    ]
    if category == "selector":
        suggested_changes[0] = "Add selector validation checks against current page DOM before click/interaction steps."
    elif category == "session/login":
        suggested_changes[0] = "Add session-readiness gate before launching workflows that require authentication."
    elif category == "timeout":
        suggested_changes[0] = "Introduce dynamic timeout policy based on workflow complexity and worker health."

    proposal = {
        "id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "title": title,
        "rationale": f"Observed repeated failure pattern in category={category}.",
        "suggested_changes": suggested_changes,
        "evidence": [
            f"Recent failures in same category: {len(recent_same_category)}",
            str(normalized.get("supporting_evidence") or ""),
        ],
        "linked_reflection_ids": [str(item.get("id")) for item in recent_same_category[-3:]],
        "status": "pending_review",
        "risk_level": "medium",
    }
    return proposal


def _record_task_outcome_learning(task: dict, outcome: str, machine_uuid: str | None, error_text: str | None = None) -> dict[str, Any]:
    reflection = _build_task_reflection(task, outcome=outcome, machine_uuid=machine_uuid, error_text=error_text)
    reflection = _normalize_reflection_record(reflection)
    _append_task_reflection(reflection)

    memory_kind = "task_success" if outcome == "success" else "task_failure"
    summary = (
        f"Task {task.get('id')} completed on worker {machine_uuid or 'unknown'}"
        if outcome == "success"
        else f"Task {task.get('id')} failed on worker {machine_uuid or 'unknown'}"
    )
    details = {
        "task_id": task.get("id"),
        "task_type": (task.get("payload") or {}).get("task_type"),
        "workflow_name": reflection.get("workflow_name"),
        "machine_uuid": machine_uuid,
        "worker_name": reflection.get("worker_name"),
        "error": error_text,
        "reflection_id": reflection.get("id"),
    }
    tags = ["task", str(outcome)]
    if error_text:
        tags.append(_extract_failure_category(error_text))
    _record_operational_memory(memory_kind, summary, details=details, tags=tags)

    proposal = _generate_improvement_proposal_from_reflection(reflection)
    if proposal is not None:
        _append_improvement_proposal(proposal)
        _record_operational_memory(
            "proposal_generated",
            f"Generated improvement proposal: {proposal.get('title')}",
            details={"proposal_id": proposal.get("proposal_id"), "status": proposal.get("status")},
            tags=["proposal", "pending_review"],
        )

    workflow_name = str(reflection.get("workflow_name") or "").strip() or None
    _run_phase3_adaptive_analysis(workflow_name)

    return reflection


@app.get("/api/workflows", response_model=list[WorkflowRecord])
def list_workflows() -> list[WorkflowRecord]:
    return WORKFLOW_REGISTRY


@app.get("/api/brain/audit")
def list_brain_audit(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 500))
    return brain_audit_log[-safe_limit:]


@app.get("/api/brain/memory", response_model=list[OperationalMemoryRecord])
def list_operational_memory(limit: int = 50, kind: str | None = None) -> list[OperationalMemoryRecord]:
    safe_limit = max(1, min(limit, 500))
    records = operational_memory_log
    if kind:
        needle = kind.strip().lower()
        records = [item for item in records if str(item.get("kind") or "").strip().lower() == needle]
    return [OperationalMemoryRecord(**item) for item in records[-safe_limit:]]


@app.get("/api/brain/reflections", response_model=list[TaskReflectionRecord])
def list_task_reflections(
    limit: int = 50,
    workflow_name: str | None = None,
    worker_name: str | None = None,
    status: str | None = None,
    date: str | None = None,
    keywords: str | None = None,
) -> list[TaskReflectionRecord]:
    safe_limit = max(1, min(limit, 500))
    records = _search_reflections(
        workflow_name=workflow_name,
        worker_name=worker_name,
        status=status,
        date=date,
        keywords=keywords,
    )
    return [TaskReflectionRecord(**item) for item in records[:safe_limit]]


@app.get("/api/brain/reflections/search", response_model=list[TaskReflectionRecord])
def search_task_reflections(
    workflow_name: str | None = None,
    worker_name: str | None = None,
    status: str | None = None,
    date: str | None = None,
    keywords: str | None = None,
    limit: int = 50,
) -> list[TaskReflectionRecord]:
    safe_limit = max(1, min(limit, 500))
    records = _search_reflections(
        workflow_name=workflow_name,
        worker_name=worker_name,
        status=status,
        date=date,
        keywords=keywords,
    )
    return [TaskReflectionRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/reflections/{reflection_id}/feedback", response_model=TaskReflectionRecord)
def add_reflection_recommendation_feedback(reflection_id: str, payload: ProposalFeedbackRequest) -> TaskReflectionRecord:
    allowed_feedback = {"helpful", "not helpful", "worked", "did not work"}
    feedback = str(payload.feedback or "").strip().lower()
    if feedback not in allowed_feedback:
        raise HTTPException(status_code=400, detail=f"Invalid feedback. Allowed: {sorted(allowed_feedback)}")

    for idx, item in enumerate(task_reflections):
        normalized = _normalize_reflection_record(item)
        if str(normalized.get("id") or "") != reflection_id:
            continue
        values = [str(x) for x in (normalized.get("recommendation_feedback") or [])]
        values.append(feedback)
        normalized["recommendation_feedback"] = values[-50:]
        task_reflections[idx] = normalized
        _save_json_list(REFLECTIONS_PATH, task_reflections)
        _record_operational_memory(
            "recommendation_feedback_recorded",
            f"Feedback '{feedback}' recorded for reflection {reflection_id}",
            details={"reflection_id": reflection_id, "feedback": feedback},
            tags=["reflection", "feedback"],
        )
        return TaskReflectionRecord(**normalized)
    raise HTTPException(status_code=404, detail="Reflection not found")


@app.get("/api/brain/reflections/{reflection_id}/explain")
def explain_reflection(reflection_id: str) -> dict:
    """Return a human-readable explanation for a specific reflection record."""
    for item in task_reflections:
        normalized = _normalize_reflection_record(item)
        if str(normalized.get("id") or "") != reflection_id:
            continue
        # Return stored explanation if present
        stored = normalized.get("human_explanation")
        if stored:
            return {
                "reflection_id": reflection_id,
                "human_summary": normalized.get("human_summary"),
                "explanation": stored,
                "technical": {
                    "failure_classification": normalized.get("failure_classification"),
                    "failure_stage": normalized.get("failure_stage"),
                    "likely_root_cause": normalized.get("likely_root_cause"),
                    "supporting_evidence": normalized.get("supporting_evidence"),
                    "retry_strategy": normalized.get("retry_strategy"),
                    "potential_fix": normalized.get("potential_fix"),
                    "confidence": normalized.get("confidence"),
                },
            }
        # Generate on-the-fly for older records without stored explanation
        category = classify_error(normalized.get("supporting_evidence"))
        similar = find_similar_failure(
            task_reflections,
            category=category,
            workflow_name=normalized.get("workflow_name"),
            current_task_id=normalized.get("task_id"),
        )
        explanation = generate_explanation(category, error_text=normalized.get("supporting_evidence"), similar_failure=similar)
        human_summary = build_human_summary(
            category,
            normalized.get("workflow_name"),
            normalized.get("worker_name"),
            str(normalized.get("status") or "unknown"),
        )
        return {
            "reflection_id": reflection_id,
            "human_summary": human_summary,
            "explanation": explanation,
            "technical": {
                "failure_classification": normalized.get("failure_classification"),
                "failure_stage": normalized.get("failure_stage"),
                "likely_root_cause": normalized.get("likely_root_cause"),
                "supporting_evidence": normalized.get("supporting_evidence"),
                "retry_strategy": normalized.get("retry_strategy"),
                "potential_fix": normalized.get("potential_fix"),
                "confidence": normalized.get("confidence"),
            },
        }
    raise HTTPException(status_code=404, detail="Reflection not found")


@app.get("/api/tasks/{task_id}/explain")
def explain_task(task_id: str) -> dict:
    """Return a human-readable explanation for the most recent reflection tied to a task."""
    task_obj = next((t for t in tasks if str(t.get("id") or "") == task_id), None)
    if task_obj is None:
        raise HTTPException(status_code=404, detail="Task not found")

    reflection = _find_reflection_by_task_id(task_id)
    error_text = task_obj.get("error") or (reflection.get("supporting_evidence") if reflection else None)
    category = classify_error(error_text)
    workflow_name = (task_obj.get("payload") or {}).get("workflow_name")
    worker_name = _worker_name_from_uuid(task_obj.get("assigned_machine_uuid"))
    status = str(task_obj.get("status") or "unknown")

    is_failed = status in ("failed", "error")

    similar = find_similar_failure(
        task_reflections,
        category=category,
        workflow_name=workflow_name,
        current_task_id=task_id,
    ) if is_failed else None

    explanation = generate_explanation(category, error_text=error_text, similar_failure=similar) if is_failed else None
    human_summary = build_human_summary(category, workflow_name, worker_name, status)

    return {
        "task_id": task_id,
        "human_summary": human_summary,
        "explanation": explanation,
        "technical": {
            "error": error_text,
            "status": status,
            "failure_classification": category if is_failed else None,
            "reflection_id": reflection.get("id") if reflection else None,
        },
    }


@app.get("/api/brain/proposals", response_model=list[ImprovementProposalRecord])
def list_improvement_proposals(
    limit: int = 50,
    status: str | None = None,
    workflow_name: str | None = None,
    proposal_type: str | None = None,
) -> list[ImprovementProposalRecord]:
    safe_limit = max(1, min(limit, 500))
    _normalize_all_proposals()
    records = list(improvement_proposals)
    if status:
        needle = status.strip().lower()
        records = [item for item in records if str(item.get("status") or "").strip().lower() == needle]
    if workflow_name:
        needle = workflow_name.strip().lower()
        records = [item for item in records if str(item.get("workflow_name") or "").strip().lower() == needle]
    if proposal_type:
        needle = proposal_type.strip().lower()
        records = [item for item in records if str(item.get("proposal_type") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return [ImprovementProposalRecord(**_normalize_proposal_record(item)) for item in records[:safe_limit]]


@app.post("/api/brain/proposals/{proposal_id}/status", response_model=ImprovementProposalRecord)
def update_improvement_proposal_status(proposal_id: str, payload: ProposalStatusUpdateRequest) -> ImprovementProposalRecord:
    allowed_status = {"open", "approved", "rejected", "deferred"}
    requested = str(payload.status or "").strip().lower()
    if requested not in allowed_status:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {sorted(allowed_status)}")

    _normalize_all_proposals()
    for idx, item in enumerate(improvement_proposals):
        normalized = _normalize_proposal_record(item)
        if str(normalized.get("proposal_id") or "") != proposal_id:
            continue
        normalized["status"] = requested
        improvement_proposals[idx] = normalized
        _save_json_list(PROPOSALS_PATH, improvement_proposals)
        _record_operational_memory(
            "proposal_status_updated",
            f"Proposal {proposal_id} marked as {requested}",
            details={"proposal_id": proposal_id, "status": requested},
            tags=["proposal", "review_queue"],
        )
        return ImprovementProposalRecord(**normalized)
    raise HTTPException(status_code=404, detail="Proposal not found")


@app.post("/api/brain/proposals/{proposal_id}/feedback", response_model=ImprovementProposalRecord)
def add_improvement_proposal_feedback(proposal_id: str, payload: ProposalFeedbackRequest) -> ImprovementProposalRecord:
    allowed_feedback = {"helpful", "not helpful", "worked", "did not work"}
    feedback = str(payload.feedback or "").strip().lower()
    if feedback not in allowed_feedback:
        raise HTTPException(status_code=400, detail=f"Invalid feedback. Allowed: {sorted(allowed_feedback)}")

    _normalize_all_proposals()
    for idx, item in enumerate(improvement_proposals):
        normalized = _normalize_proposal_record(item)
        if str(normalized.get("proposal_id") or "") != proposal_id:
            continue
        feedback_list = [str(x) for x in (normalized.get("feedback") or [])]
        feedback_list.append(feedback)
        normalized["feedback"] = feedback_list[-50:]
        improvement_proposals[idx] = normalized
        _save_json_list(PROPOSALS_PATH, improvement_proposals)
        _record_operational_memory(
            "proposal_feedback_recorded",
            f"Feedback '{feedback}' recorded for proposal {proposal_id}",
            details={"proposal_id": proposal_id, "feedback": feedback},
            tags=["proposal", "feedback"],
        )
        return ImprovementProposalRecord(**normalized)
    raise HTTPException(status_code=404, detail="Proposal not found")


@app.get("/api/brain/interactions", response_model=list[InteractivePromptRecord])
def list_interactions(status: str | None = None, limit: int = 50) -> list[InteractivePromptRecord]:
    safe_limit = max(1, min(limit, 500))
    records = list(interactive_prompts)
    if status:
        needle = status.strip().lower()
        records = [item for item in records if str(item.get("status") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return [InteractivePromptRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/interactions/{interaction_id}/decision", response_model=InteractivePromptRecord)
def decide_interaction(interaction_id: str, payload: InteractivePromptDecisionRequest) -> InteractivePromptRecord:
    interaction = _find_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Interaction not found")
    if str(interaction.get("status") or "") not in {"pending", "paused"}:
        raise HTTPException(status_code=400, detail="Interaction is no longer actionable")

    merged_adjustments = dict(interaction.get("pending_adjustments") or {})
    merged_adjustments.update(payload.adjustments or {})

    if not payload.approved:
        interaction["status"] = "rejected"
        interaction["updated_at"] = datetime.utcnow().isoformat()
        if payload.notes:
            interaction["notes"] = payload.notes
        _save_interactive_prompts()
        return InteractivePromptRecord(**interaction)

    workflow_name = str((interaction.get("metadata") or {}).get("workflow_name") or "")
    target_machine_uuid = str((interaction.get("metadata") or {}).get("target_machine_uuid") or "") or None
    if not workflow_name:
        interaction["status"] = "approved"
        interaction["updated_at"] = datetime.utcnow().isoformat()
        if payload.notes:
            interaction["notes"] = payload.notes
        _save_interactive_prompts()
        return InteractivePromptRecord(**interaction)

    task = _create_workflow_task(workflow_name, target_machine_uuid=target_machine_uuid, extra_payload=merged_adjustments)
    interaction["status"] = "executed"
    interaction["task_id"] = task.id
    interaction["updated_at"] = datetime.utcnow().isoformat()
    if payload.notes:
        interaction["notes"] = payload.notes
    _save_interactive_prompts()

    _record_operational_memory(
        "interactive_execution",
        f"Approved interaction {interaction_id} executed workflow {workflow_name}",
        details={"interaction_id": interaction_id, "workflow_name": workflow_name, "task_id": task.id},
        tags=["interaction", "phase4"],
    )

    return InteractivePromptRecord(**interaction)


@app.post("/api/brain/guided/start", response_model=InteractivePromptRecord)
def start_guided_execution(payload: GuidedExecutionStartRequest) -> InteractivePromptRecord:
    workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == payload.workflow_name), None)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    answers = dict(payload.initial_answers or {})
    missing_inputs = [name for name in (workflow.required_inputs or []) if name not in answers]
    questions = [f"Provide value for: {name}" for name in missing_inputs]
    if workflow.login_or_session_required:
        questions.append("Confirm authenticated session on selected worker (yes/no).")

    prompt = _create_interaction_prompt(
        interaction_type="guided_execution",
        command=f"guided:{payload.workflow_name}",
        recommendation=f"Guided execution started for {payload.workflow_name}.",
        questions=questions,
        pending_adjustments=answers,
        metadata={
            "workflow_name": payload.workflow_name,
            "target_machine_uuid": payload.target_machine_uuid,
            "answers": answers,
        },
    )
    return InteractivePromptRecord(**prompt)


@app.post("/api/brain/guided/{interaction_id}/answer", response_model=InteractivePromptRecord)
def answer_guided_execution(interaction_id: str, payload: GuidedExecutionAnswerRequest) -> InteractivePromptRecord:
    interaction = _find_interaction(interaction_id)
    if not interaction:
        raise HTTPException(status_code=404, detail="Guided interaction not found")
    if str(interaction.get("interaction_type") or "") != "guided_execution":
        raise HTTPException(status_code=400, detail="Interaction is not guided execution")

    metadata = dict(interaction.get("metadata") or {})
    answers = dict(metadata.get("answers") or {})
    answers.update(payload.answers or {})
    metadata["answers"] = answers
    interaction["metadata"] = metadata
    interaction["pending_adjustments"] = answers

    workflow_name = str(metadata.get("workflow_name") or "")
    workflow = next((record for record in WORKFLOW_REGISTRY if record.workflow_name == workflow_name), None)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    missing_inputs = [name for name in (workflow.required_inputs or []) if name not in answers]
    if missing_inputs or not payload.continue_execution:
        interaction["status"] = "paused"
        interaction["questions"] = [f"Provide value for: {name}" for name in missing_inputs]
        interaction["updated_at"] = datetime.utcnow().isoformat()
        _save_interactive_prompts()
        return InteractivePromptRecord(**interaction)

    target_machine_uuid = str(metadata.get("target_machine_uuid") or "") or None
    task = _create_workflow_task(workflow_name, target_machine_uuid=target_machine_uuid, extra_payload=answers)
    interaction["status"] = "executed"
    interaction["task_id"] = task.id
    interaction["questions"] = []
    interaction["updated_at"] = datetime.utcnow().isoformat()
    _save_interactive_prompts()
    return InteractivePromptRecord(**interaction)


@app.post("/api/brain/proposals/{proposal_id}/run", response_model=TaskCreateResponse)
def run_with_improvement(proposal_id: str, payload: RunWithImprovementRequest) -> TaskCreateResponse:
    _normalize_all_proposals()
    proposal = next(
        (
            _normalize_proposal_record(item)
            for item in improvement_proposals
            if str(_normalize_proposal_record(item).get("proposal_id") or "") == proposal_id
        ),
        None,
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    recommendation_adjustments = _recommended_change_to_adjustments(str(proposal.get("recommended_change") or ""))
    merged = dict(recommendation_adjustments)
    merged.update(payload.runtime_adjustments or {})
    merged["run_with_improvement"] = True
    merged["improvement_proposal_id"] = proposal_id

    if _has_non_trivial_adjustments(merged) and not payload.confirm_execution:
        raise HTTPException(status_code=400, detail="confirm_execution=true required for non-trivial runtime changes")

    workflow_name = str(proposal.get("workflow_name") or "")
    if not workflow_name:
        raise HTTPException(status_code=400, detail="Proposal missing workflow name")

    task = _create_workflow_task(workflow_name, target_machine_uuid=payload.target_machine_uuid, extra_payload=merged)
    _attach_live_reasoning(task.id, [f"Run with improvement proposal {proposal_id}"])
    return task


@app.get("/api/brain/preferences", response_model=list[ConversationPreferenceRecord])
def list_conversation_preferences() -> list[ConversationPreferenceRecord]:
    ordered = sorted(conversation_preferences, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return [ConversationPreferenceRecord(**item) for item in ordered]


@app.put("/api/brain/preferences", response_model=ConversationPreferenceRecord)
def update_conversation_preference(payload: ConversationPreferenceUpdateRequest) -> ConversationPreferenceRecord:
    updated = _set_conversation_preference(payload.key, payload.value)
    _record_operational_memory(
        "conversation_preference",
        f"Updated preference {payload.key}",
        details={"key": payload.key, "value": payload.value},
        tags=["conversation", "preference"],
    )
    return ConversationPreferenceRecord(**updated)


@app.get("/api/brain/workflow-learning/drafts", response_model=list[WorkflowLearningDraftRecord])
def list_workflow_learning_drafts(limit: int = 100, review_status: str | None = None) -> list[WorkflowLearningDraftRecord]:
    _normalize_all_workflow_drafts()
    safe_limit = max(1, min(limit, 500))
    records = list(workflow_learning_drafts)
    if review_status:
        needle = review_status.strip().lower()
        records = [item for item in records if str(item.get("review_status") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return [WorkflowLearningDraftRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/workflow-learning/drafts", response_model=WorkflowLearningDraftRecord)
def create_workflow_learning_draft(payload: WorkflowLearningCreateRequest) -> WorkflowLearningDraftRecord:
    draft = _build_workflow_draft(payload)
    workflow_learning_drafts.append(draft)
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_created",
        f"Created workflow learning draft {draft.get('draft_id')} for {draft.get('workflow_name')}",
        details={"draft_id": draft.get("draft_id"), "workflow_name": draft.get("workflow_name"), "path": draft.get("learning_path")},
        tags=["workflow_learning", "draft"],
    )
    return WorkflowLearningDraftRecord(**draft)


@app.put("/api/brain/workflow-learning/drafts/{draft_id}/status", response_model=WorkflowLearningDraftRecord)
def update_workflow_learning_draft_status(draft_id: str, payload: WorkflowDraftStatusUpdateRequest) -> WorkflowLearningDraftRecord:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    allowed = {"draft", "testing", "in_review", "approved", "rejected", "published"}
    next_status = str(payload.review_status or "").strip().lower()
    if next_status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid review_status. Allowed: {sorted(allowed)}")

    updated = dict(draft)
    updated["review_status"] = next_status
    if payload.reviewer_notes is not None:
        updated["reviewer_notes"] = payload.reviewer_notes
    updated["updated_at"] = datetime.utcnow().isoformat()
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    return WorkflowLearningDraftRecord(**updated)


@app.delete("/api/brain/workflow-learning/drafts/{draft_id}")
def delete_workflow_learning_draft(draft_id: str) -> dict[str, str]:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    removed = workflow_learning_drafts.pop(idx)
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_deleted",
        f"Deleted workflow learning draft {draft_id}",
        details={"draft_id": draft_id, "workflow_name": removed.get("workflow_name")},
        tags=["workflow_learning", "draft", "delete"],
    )
    return {"deleted_draft_id": draft_id}


@app.put("/api/brain/workflow-learning/drafts/{draft_id}/structure", response_model=WorkflowLearningDraftRecord)
def update_workflow_learning_draft_structure(
    draft_id: str,
    payload: WorkflowDraftStructureUpdateRequest,
) -> WorkflowLearningDraftRecord:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    updated = dict(draft)
    if payload.steps is not None:
        normalized_steps = [_normalize_step(step, order) for order, step in enumerate(payload.steps, start=1)]
        updated["steps"] = normalized_steps

    if payload.variables is not None:
        # Caller supplies explicit variable definitions; merge with any derived from steps
        caller_vars: dict[str, dict] = {}
        for raw_var in payload.variables:
            v = dict(raw_var) if isinstance(raw_var, dict) else raw_var.dict()
            key = str(v.get("field_key") or "")
            if key:
                caller_vars[key] = v
        # Fill in any step-captured variables not already in caller's list
        for step in updated.get("steps") or []:
            for var in step.get("variable_inputs") or []:
                k = str(var.get("field_key") or "")
                if k and k not in caller_vars:
                    caller_vars[k] = dict(var)
        updated["variables"] = list(caller_vars.values())

    if payload.required_inputs is not None:
        updated["required_inputs"] = [str(x).strip() for x in payload.required_inputs if str(x).strip()]
    elif payload.steps is not None:
        derived_inputs: list[str] = []
        for step in updated.get("steps") or []:
            for variable in step.get("variable_inputs") or []:
                if bool(variable.get("required_input")):
                    key = str(variable.get("field_key") or "").strip()
                    if key and key not in derived_inputs:
                        derived_inputs.append(key)
        updated["required_inputs"] = derived_inputs

    if payload.validation_rules is not None:
        updated["validation_rules"] = [str(x).strip() for x in payload.validation_rules if str(x).strip()]

    if payload.fallback_strategies is not None:
        updated["fallback_strategies"] = [str(x).strip() for x in payload.fallback_strategies if str(x).strip()]

    if payload.common_failures is not None:
        updated["common_failures"] = [str(x).strip() for x in payload.common_failures if str(x).strip()]

    updated["updated_at"] = datetime.utcnow().isoformat()
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_structure_updated",
        f"Updated structured learning details for draft {draft_id}",
        details={"draft_id": draft_id, "workflow_name": updated.get("workflow_name")},
        tags=["workflow_learning", "draft", "structure"],
    )
    return WorkflowLearningDraftRecord(**updated)


@app.get("/api/brain/workflow-learning/drafts/{draft_id}/teach", response_model=TeachingSessionQuestion)
def get_workflow_teaching_question(draft_id: str) -> TeachingSessionQuestion:
    """Return questions for the next step that still needs teaching enrichment."""
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    if bool(draft.get("teaching_complete")):
        return TeachingSessionQuestion(
            draft_id=draft_id,
            step_order=0,
            step_name="",
            questions=[],
            teaching_complete=True,
            steps_remaining=0,
        )

    pending_step_order = draft.get("teaching_pending_step")
    steps = [s for s in (draft.get("steps") or []) if isinstance(s, dict)]
    if not steps or pending_step_order is None:
        return TeachingSessionQuestion(
            draft_id=draft_id,
            step_order=0,
            step_name="",
            questions=[],
            teaching_complete=True,
            steps_remaining=0,
        )

    target_step: dict[str, Any] | None = None
    for s in steps:
        if int(s.get("step_order") or 0) == int(pending_step_order):
            target_step = s
            break
    if target_step is None:
        target_step = steps[0]

    all_orders = sorted(int(s.get("step_order") or 0) for s in steps)
    current_order = int(target_step.get("step_order") or 0)
    steps_remaining = sum(1 for o in all_orders if o > current_order)

    question = _generate_step_teaching_questions(target_step, draft_id)
    question.steps_remaining = steps_remaining
    return question


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/teach", response_model=TeachingSessionQuestion)
def submit_workflow_teaching_answers(
    draft_id: str,
    payload: TeachingSessionAnswerRequest,
) -> TeachingSessionQuestion:
    """Accept teaching answers for a step, enrich the draft, and return the next question."""
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    answer_dicts = [a.dict() if hasattr(a, "dict") else dict(a) for a in (payload.answers or [])]
    updated = _apply_step_teaching_answers(draft, int(payload.step_order), answer_dicts)
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_teaching_step_answered",
        f"Teaching answers applied to step {payload.step_order} of draft {draft_id}",
        details={"draft_id": draft_id, "step_order": payload.step_order},
        tags=["workflow_learning", "teaching"],
    )

    if bool(updated.get("teaching_complete")):
        return TeachingSessionQuestion(
            draft_id=draft_id,
            step_order=0,
            step_name="",
            questions=[],
            teaching_complete=True,
            steps_remaining=0,
        )

    # Return the next step's questions
    next_order = updated.get("teaching_pending_step")
    steps = [s for s in (updated.get("steps") or []) if isinstance(s, dict)]
    target_step: dict[str, Any] | None = None
    for s in steps:
        if int(s.get("step_order") or 0) == int(next_order or 0):
            target_step = s
            break
    if target_step is None:
        return TeachingSessionQuestion(
            draft_id=draft_id, step_order=0, step_name="", questions=[], teaching_complete=True, steps_remaining=0
        )

    all_orders = sorted(int(s.get("step_order") or 0) for s in steps)
    current_order = int(target_step.get("step_order") or 0)
    steps_remaining = sum(1 for o in all_orders if o > current_order)
    question = _generate_step_teaching_questions(target_step, draft_id)
    question.steps_remaining = steps_remaining
    return question


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/test", response_model=TaskCreateResponse)
def test_workflow_learning_draft(draft_id: str, payload: WorkflowDraftTestRequest) -> TaskCreateResponse:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    executable_steps = _to_executable_browser_steps(list(draft.get("steps") or []))
    runtime_payload = {
        "task_type": "browser_workflow",
        "mode": "interactive_visible" if payload.guided_mode else "headless_background",
        "steps": executable_steps,
        "workflow_name": f"draft::{draft.get('workflow_name')}",
        "workflow_learning_draft_id": draft_id,
        "guided_draft_test": bool(payload.guided_mode),
        "runtime_adjustments": payload.runtime_adjustments or {},
    }
    if payload.target_machine_uuid:
        runtime_payload["target_machine_uuid"] = payload.target_machine_uuid
    if payload.runtime_adjustments:
        runtime_payload.update(payload.runtime_adjustments)

    task = _create_task_record(runtime_payload)

    updated = dict(draft)
    updated["review_status"] = "testing"
    updated["updated_at"] = datetime.utcnow().isoformat()
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()
    _record_operational_memory(
        "workflow_learning_draft_test_queued",
        f"Queued guided test for draft {draft_id}",
        details={"draft_id": draft_id, "task_id": task.id},
        tags=["workflow_learning", "testing"],
    )
    return task


@app.post("/api/brain/workflow-learning/drafts/{draft_id}/publish", response_model=WorkflowLearningDraftRecord)
def publish_workflow_learning_draft(draft_id: str, payload: WorkflowDraftPublishRequest) -> WorkflowLearningDraftRecord:
    idx, draft = _find_workflow_draft(draft_id)
    if draft is None or idx is None:
        raise HTTPException(status_code=404, detail="Workflow draft not found")

    status = str(draft.get("review_status") or "").strip().lower()
    if status != "approved":
        raise HTTPException(status_code=400, detail="Draft must be in approved status before publish")

    workflow_name = str(draft.get("workflow_name") or "").strip()
    if not workflow_name:
        raise HTTPException(status_code=400, detail="Draft workflow_name is required")

    executable_steps = _to_executable_browser_steps(list(draft.get("steps") or []))

    workflow_record = WorkflowRecord(
        workflow_name=workflow_name,
        description=str(draft.get("description") or draft.get("goal") or workflow_name),
        required_inputs=[str(item) for item in (draft.get("required_inputs") or [])],
        login_or_session_required=bool(draft.get("required_session_state")),
        safe_for_unattended=bool(draft.get("safe_for_unattended", False)),
        compatible_worker_types=["interactive_visible", "headless_background"],
        procedure_name=workflow_name,
    )

    existing_idx = next((i for i, item in enumerate(WORKFLOW_REGISTRY) if item.workflow_name == workflow_name), None)
    if existing_idx is None:
        WORKFLOW_REGISTRY.append(workflow_record)
    else:
        WORKFLOW_REGISTRY[existing_idx] = workflow_record
    _save_workflow_registry()

    template = {
        "name": workflow_name,
        "task_type": "browser_workflow",
        "description": str(draft.get("description") or draft.get("goal") or workflow_name),
        "payload": {
            "task_type": "browser_workflow",
            "mode": "interactive_visible",
            "step_delay_ms": 800,
            "steps": executable_steps,
            "workflow_learning_source": "published_draft",
        },
    }
    PROCEDURE_TEMPLATES[workflow_name] = template
    learned_existing_idx = next((i for i, item in enumerate(learned_procedure_templates) if str(item.get("name") or "") == workflow_name), None)
    if learned_existing_idx is None:
        learned_procedure_templates.append(template)
    else:
        learned_procedure_templates[learned_existing_idx] = template
    _save_learned_procedure_templates()

    updated = dict(draft)
    updated["review_status"] = "published"
    updated["published_workflow_name"] = workflow_name
    updated["updated_at"] = datetime.utcnow().isoformat()
    notes = [str(updated.get("reviewer_notes") or "").strip()]
    if payload.approved_by:
        notes.append(f"published_by={payload.approved_by}")
    if payload.publish_notes:
        notes.append(payload.publish_notes)
    updated["reviewer_notes"] = " | ".join([item for item in notes if item])
    workflow_learning_drafts[idx] = updated
    _save_workflow_learning_drafts()

    _record_operational_memory(
        "workflow_learning_draft_published",
        f"Published learned workflow {workflow_name} from draft {draft_id}",
        details={"draft_id": draft_id, "workflow_name": workflow_name},
        tags=["workflow_learning", "published", "review_required"],
    )
    return WorkflowLearningDraftRecord(**updated)


@app.get("/api/brain/sop", response_model=list[WorkflowSOPSummaryRecord])
def list_workflow_sop_summaries(workflow_name: str | None = None, limit: int = 100) -> list[WorkflowSOPSummaryRecord]:
    safe_limit = max(1, min(limit, 500))
    records = list(workflow_sop_summaries)
    if workflow_name:
        needle = workflow_name.strip().lower()
        records = [item for item in records if str(item.get("workflow_name") or "").strip().lower() == needle]
    records = sorted(records, key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return [WorkflowSOPSummaryRecord(**item) for item in records[:safe_limit]]


@app.post("/api/brain/sop/{workflow_name}", response_model=WorkflowSOPSummaryRecord)
def regenerate_workflow_sop_summary(workflow_name: str) -> WorkflowSOPSummaryRecord:
    summary = _update_sop_summary_for_workflow(workflow_name)
    if summary is None:
        raise HTTPException(status_code=404, detail="No reflections found for workflow")
    return WorkflowSOPSummaryRecord(**summary)


@app.put("/api/brain/sop/{workflow_name}", response_model=WorkflowSOPSummaryRecord)
def update_workflow_sop_summary(workflow_name: str, payload: WorkflowSOPUpdateRequest) -> WorkflowSOPSummaryRecord:
    existing_idx = next(
        (idx for idx, item in enumerate(workflow_sop_summaries) if str(item.get("workflow_name") or "") == workflow_name),
        None,
    )
    if existing_idx is None:
        summary = _update_sop_summary_for_workflow(workflow_name)
        if summary is None:
            raise HTTPException(status_code=404, detail="No reflections found for workflow")
        existing_idx = next(
            (idx for idx, item in enumerate(workflow_sop_summaries) if str(item.get("workflow_name") or "") == workflow_name),
            None,
        )
        if existing_idx is None:
            raise HTTPException(status_code=500, detail="Failed to initialize SOP summary")

    current = dict(workflow_sop_summaries[existing_idx])
    if payload.purpose is not None:
        current["purpose"] = payload.purpose
    if payload.prerequisites is not None:
        current["prerequisites"] = payload.prerequisites
    if payload.normal_flow is not None:
        current["normal_flow"] = payload.normal_flow
    if payload.common_failures is not None:
        current["common_failures"] = payload.common_failures
    if payload.recommended_fixes is not None:
        current["recommended_fixes"] = payload.recommended_fixes
    if payload.best_worker_patterns is not None:
        current["best_worker_patterns"] = payload.best_worker_patterns
    current["updated_at"] = datetime.utcnow().isoformat()

    workflow_sop_summaries[existing_idx] = current
    _save_workflow_sop_summaries()
    _record_operational_memory(
        "sop_updated",
        f"SOP summary updated for workflow={workflow_name}",
        details={"workflow_name": workflow_name},
        tags=["sop", "manual_update"],
    )
    return WorkflowSOPSummaryRecord(**current)


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
    decision_reasoning: list[str] = []
    preflight_warnings: list[str] = []
    requires_confirmation = False
    pending_interaction_id: str | None = None
    pending_questions: list[str] = []

    worker_hint_match = re.search(r"on worker\s+(.+)$", command_text, flags=re.IGNORECASE)
    worker_hint = worker_hint_match.group(1).strip() if worker_hint_match else None

    if payload.target_machine_uuid:
        selected_worker = _find_worker_by_hint(machines, payload.target_machine_uuid)
    elif worker_hint:
        selected_worker = _find_worker_by_hint(machines, worker_hint)

    preference_updates = _parse_conversation_preference_updates(command_text)
    if preference_updates:
        recognized_intent = "conversation_preference_update"
        before_execution = "I parsed preference updates from your conversation command."
        labels: list[str] = []
        for item in preference_updates:
            stored = _set_conversation_preference(str(item["key"]), item["value"])
            labels.append(f"{stored.get('key')}={stored.get('value')}")
        after_execution = "Saved conversation preferences: " + "; ".join(labels)
        suggested_next_action = "These preferences will influence worker choice and runtime adjustments."

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
            reflection = _find_reflection_by_task_id(str(failed.get("id") or ""))
            after_execution = (
                f"Last failed task: {failed.get('id')} type={(failed.get('payload') or {}).get('task_type', 'unknown')} "
                f"worker={failed.get('assigned_machine_uuid') or 'unassigned'} error={failed.get('error') or 'no error text'}"
            )
            if reflection:
                after_execution += (
                    f" Retry strategy: {reflection.get('retry_strategy') or 'retry once with reduced scope'}."
                    f" Alternative worker: {reflection.get('alternative_worker') or 'none_available'}."
                    f" Potential fix: {reflection.get('potential_fix') or 'inspect logs and selectors'}."
                )
            retry_recommended = True
            suggested_next_action = "Say 'retry last failed task' to queue it again."
        else:
            after_execution = "I did not find any failed tasks in recent history."
            suggested_next_action = "You can ask me to run a workflow now."

    elif "why did this fail" in command_lower or "why did it fail" in command_lower:
        recognized_intent = "memory_failure_reason"
        before_execution = "I searched reflection memory for the latest matching failed run."
        workflow_hint = _extract_workflow_hint(command_text)
        reflection_records = _search_reflections(workflow_name=workflow_hint, status="failed")
        if reflection_records:
            top = reflection_records[0]
            after_execution = (
                f"Likely root cause: {top.get('likely_root_cause')} "
                f"(stage={top.get('failure_stage') or 'unknown'}, worker={top.get('worker_name') or 'unknown'}). "
                f"Evidence: {top.get('supporting_evidence')}"
            )
            after_execution += (
                f" Retry strategy: {top.get('retry_strategy') or 'retry once with reduced scope'}."
                f" Alternative worker: {top.get('alternative_worker') or 'none_available'}."
                f" Potential fix: {top.get('potential_fix') or 'inspect worker logs for details'}."
            )
            suggested_next_action = str(top.get("recommended_next_action") or "Retry with suggested mitigation.")
            retry_recommended = True
        else:
            after_execution = "I do not have a matching failed reflection yet."
            suggested_next_action = "Run the workflow once so reflection memory can learn this failure mode."

    elif "have we seen this before" in command_lower:
        recognized_intent = "memory_seen_before"
        before_execution = "I compared recent reflection history for similar failures."
        workflow_hint = _extract_workflow_hint(command_text)
        keywords = None
        if "timeout" in command_lower:
            keywords = "timeout"
        elif "selector" in command_lower or "element" in command_lower:
            keywords = "selector"
        elif "login" in command_lower or "session" in command_lower:
            keywords = "login session"

        matches = _search_reflections(workflow_name=workflow_hint, status="failed", keywords=keywords)
        if matches:
            after_execution = f"Yes. I found {len(matches)} similar failed run(s) in reflection memory."
            latest = matches[0]
            after_execution += f" Most recent root cause: {latest.get('likely_root_cause')}."
            suggested_next_action = str(latest.get("recommended_next_action") or "Use recent mitigation and retry.")
        else:
            after_execution = "No clear prior match found in reflection memory."
            suggested_next_action = "Capture one or two runs and ask again for trend confidence."

    elif "what usually fixes this" in command_lower or "usual fix" in command_lower:
        recognized_intent = "memory_usual_fix"
        before_execution = "I analyzed reflection recommendations from similar failures."
        workflow_hint = _extract_workflow_hint(command_text)
        failed_matches = _search_reflections(workflow_name=workflow_hint, status="failed")
        if failed_matches:
            action_counts: dict[str, int] = {}
            for item in failed_matches[:50]:
                action = str(item.get("recommended_next_action") or "").strip()
                if not action:
                    continue
                action_counts[action] = action_counts.get(action, 0) + 1
            if action_counts:
                top_action = sorted(action_counts.items(), key=lambda pair: pair[1], reverse=True)[0]
                after_execution = f"Most common successful recommendation pattern: {top_action[0]} (seen {top_action[1]} times)."
                suggested_next_action = top_action[0]
                retry_recommended = True
            else:
                after_execution = "I found failures, but no clear repeated recommendation yet."
                suggested_next_action = "Collect more run outcomes to strengthen recommendation confidence."
        else:
            after_execution = "I do not have enough failed reflections for a 'usual fix' yet."
            suggested_next_action = "Run the workflow and ask again after a few outcomes."

    elif "which worker is best" in command_lower or "best worker" in command_lower:
        recognized_intent = "memory_best_worker"
        before_execution = "I calculated worker performance from reflection history."
        workflow_hint = _extract_workflow_hint(command_text)
        workflow_records = _search_reflections(workflow_name=workflow_hint)
        stats: dict[str, dict[str, int]] = {}
        for entry in workflow_records:
            name = str(entry.get("worker_name") or "unknown")
            bucket = stats.setdefault(name, {"total": 0, "success": 0})
            bucket["total"] += 1
            if str(entry.get("status") or "").lower() == "completed":
                bucket["success"] += 1

        scored: list[tuple[str, float, int]] = []
        for worker, bucket in stats.items():
            total = bucket.get("total", 0)
            if total <= 0:
                continue
            rate = bucket.get("success", 0) / total
            scored.append((worker, rate, total))

        if scored:
            scored.sort(key=lambda row: (row[1], row[2]), reverse=True)
            best = scored[0]
            pct = round(best[1] * 100, 1)
            after_execution = f"Best worker for {workflow_hint or 'this workflow'} is {best[0]} with ~{pct}% success over {best[2]} run(s)."
            suggested_next_action = f"Target worker {best[0]} for the next run when available."
        else:
            after_execution = "Not enough reflection history to rank workers yet."
            suggested_next_action = "Run the workflow on available workers to build comparative memory."

    elif "why did you pick this worker" in command_lower or "why this worker" in command_lower:
        recognized_intent = "worker_selection_explanation"
        before_execution = "I reviewed the latest worker selection reasoning from memory-aware orchestration."
        latest = _latest_worker_selection_audit()
        if latest:
            selected_uuid = latest.get("selected_worker") or "unknown"
            selected_name = _worker_name_from_uuid(selected_uuid) or selected_uuid
            reason_text = str(latest.get("before_execution") or "No detailed reasoning was recorded.")
            after_execution = f"I picked {selected_name} because: {reason_text}"
            suggested_next_action = "Ask which worker is best for a specific workflow to compare options."
        else:
            after_execution = "I do not have a recent worker selection decision to explain yet."
            suggested_next_action = "Run a workflow first, then ask again."

    elif any(
        phrase in command_lower
        for phrase in [
            "troubleshoot",
            "why did",
            "how do i fix",
            "explain failure trend",
            "what keeps failing",
        ]
    ):
        recognized_intent = "troubleshooting"
        before_execution = "I reviewed recent failures, reflections, and recurring patterns."
        recent_failures = [
            task for task in sorted(tasks, key=lambda item: item.get("created_at", ""), reverse=True) if task.get("status") == "failed"
        ][:10]
        recent_failure_reflections = [
            item for item in _search_reflections(status="failed")[:30]
        ]

        if not recent_failures:
            after_execution = "I do not see recent failed tasks, so there is no active failure trend to troubleshoot."
            suggested_next_action = "Run a workflow and I will reflect on outcomes automatically."
        else:
            categories: dict[str, int] = {}
            for task_item in recent_failures:
                category = _extract_failure_category(task_item.get("error"))
                categories[category] = categories.get(category, 0) + 1

            top_category = sorted(categories.items(), key=lambda pair: pair[1], reverse=True)[0][0]
            related_reflection = next(
                (
                    item
                    for item in reversed(recent_failure_reflections)
                    if _extract_failure_category(item.get("supporting_evidence")) == top_category
                ),
                None,
            )
            after_execution = (
                f"Recent trend: {top_category} is the most frequent failure category "
                f"({categories.get(top_category, 0)} of the last {len(recent_failures)} failures)."
            )
            if related_reflection:
                after_execution += f" Latest reflection guidance: {related_reflection.get('recommended_next_action')}."
            suggested_next_action = "Ask me to generate improvement proposals or retry with tighter limits."
            retry_recommended = True

    elif "show reflections" in command_lower or "recent reflections" in command_lower:
        recognized_intent = "reflection_query"
        before_execution = "I reviewed recent task reflections from the adaptive memory layer."
        recent = _search_reflections()[:3]
        if recent:
            summary = " | ".join(
                f"task={item.get('task_id')} status={item.get('status')} action={item.get('recommended_next_action')}"
                for item in recent
            )
            after_execution = f"Recent reflections: {summary}"
            suggested_next_action = "Ask for a troubleshooting summary to focus on repeated failures."
        else:
            after_execution = "No reflections are recorded yet."
            suggested_next_action = "Run or retry a task so reflection entries can be generated."

    elif "show proposals" in command_lower or "list proposals" in command_lower:
        recognized_intent = "proposal_query"
        before_execution = "I checked pending and historical improvement proposals."
        recent = improvement_proposals[-5:]
        if recent:
            summary = " | ".join(
                f"{item.get('title')} (status={item.get('status')})" for item in recent
            )
            after_execution = f"Recent proposals: {summary}"
            suggested_next_action = "Review a proposal before making controlled implementation changes."
        else:
            after_execution = "No improvement proposals exist yet."
            suggested_next_action = "Ask me to generate improvement proposals from recent failures."

    elif "generate proposal" in command_lower or "propose improvement" in command_lower:
        recognized_intent = "proposal_generation"
        before_execution = "I evaluated recent failure reflections for repeatable improvement opportunities."
        recent_failures = _search_reflections(status="failed")[:30]
        created = 0
        for reflection in recent_failures[-5:]:
            proposal = _generate_improvement_proposal_from_reflection(reflection)
            if proposal is not None:
                _append_improvement_proposal(proposal)
                created += 1
        if created:
            after_execution = f"Generated {created} new proposal(s) with status=pending_review."
            suggested_next_action = "Review proposals in the audit panel before any implementation work."
        else:
            after_execution = "No new proposals were generated; either patterns are not repeated yet or proposals already exist."
            suggested_next_action = "After more task outcomes, ask again to generate proposals."

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

        is_complex_workflow = bool(workflow and (workflow.login_or_session_required or len(required_inputs) >= 2))
        if is_complex_workflow and missing_inputs:
            questions = [f"Please provide value for: {name}" for name in missing_inputs]
            if workflow and workflow.login_or_session_required:
                questions.append("Confirm session is authenticated on target worker (yes/no).")
            prompt = _create_interaction_prompt(
                interaction_type="guided_execution",
                command=command_text,
                recommendation=f"Guided execution for {selected_workflow} requires step-by-step answers.",
                questions=questions,
                pending_adjustments={},
                metadata={
                    "workflow_name": selected_workflow,
                    "target_machine_uuid": payload.target_machine_uuid,
                    "answers": dict(payload.guided_answers or {}),
                },
            )
            before_execution = "I detected a complex workflow and started guided execution."
            after_execution = "I paused before execution to collect required answers safely."
            suggested_next_action = "Answer the guided questions, then approve execution."
            requires_confirmation = True
            pending_interaction_id = str(prompt.get("interaction_id"))
            pending_questions = list(prompt.get("questions") or [])
        elif missing_inputs:
            before_execution = "I parsed your request and identified a workflow, but required inputs are missing."
            after_execution = f"Please provide required inputs: {', '.join(missing_inputs)}."
            suggested_next_action = (
                f"Try: run {selected_workflow} with "
                + " ".join(f"{name} <value>" for name in missing_inputs)
            )
            requires_confirmation = True
            pending_questions = [f"Provide input: {name}" for name in missing_inputs]
        else:
            if not selected_worker:
                preferred_worker_hint = _get_conversation_preference("preferred_worker")
                if isinstance(preferred_worker_hint, str) and preferred_worker_hint.strip():
                    selected_worker = _find_worker_by_hint(machines, preferred_worker_hint)
                    if selected_worker:
                        decision_reasoning.append("Selected preferred worker from conversation memory.")

            if not selected_worker:
                selected_worker, reason, selection_warnings = _select_best_worker_with_memory(
                    machines,
                    selected_workflow,
                    payload.target_machine_uuid,
                )
                decision_reasoning.append(reason)
                preflight_warnings.extend(selection_warnings)

            preflight_warnings.extend(_preflight_memory_warnings(selected_workflow, selected_worker))

            if workflow and workflow.login_or_session_required:
                before_execution = (
                    "This workflow requires an authenticated browser/session. "
                    "I cannot fully verify session readiness remotely, so ensure the target worker is logged in first."
                )
            else:
                before_execution = "I parsed your request, selected a workflow, and chose the best available worker."

            if selected_worker:
                extra_payload: dict[str, Any] = {}
                for key in [
                    "max_clients",
                    "max_pages",
                    "retry_failed_only",
                    "client_name",
                    "household_name",
                    "retry_count",
                    "wait_time_ms",
                    "selector_strategy",
                ]:
                    if key in command_params:
                        extra_payload[key] = command_params[key]

                if payload.runtime_adjustments:
                    extra_payload.update(payload.runtime_adjustments)
                    decision_reasoning.append("Applied runtime adjustments supplied in this command.")

                adjusted_payload, payload_reasons = _memory_adjust_workflow_parameters(selected_workflow, extra_payload)
                extra_payload = adjusted_payload
                decision_reasoning.extend(payload_reasons)

                preferred_payload, pref_reasons = _apply_conversation_preferences(selected_workflow, extra_payload)
                extra_payload = preferred_payload
                decision_reasoning.extend(pref_reasons)

                run_with_improvement = False
                proposal_id = payload.run_with_proposal_id
                proposal_adjustments: dict[str, Any] = {}
                if proposal_id:
                    _normalize_all_proposals()
                    proposal = next(
                        (
                            _normalize_proposal_record(item)
                            for item in improvement_proposals
                            if str(_normalize_proposal_record(item).get("proposal_id") or "") == proposal_id
                        ),
                        None,
                    )
                    if proposal:
                        proposal_adjustments = _recommended_change_to_adjustments(str(proposal.get("recommended_change") or ""))
                        extra_payload.update(proposal_adjustments)
                        extra_payload["run_with_improvement"] = True
                        extra_payload["improvement_proposal_id"] = proposal_id
                        run_with_improvement = True
                        decision_reasoning.append(f"Applied proposal-guided adjustments from {proposal_id}.")

                if command_params.get("worker_override"):
                    override_worker = _find_worker_by_hint(machines, str(command_params.get("worker_override")))
                    if override_worker:
                        selected_worker = override_worker
                        decision_reasoning.append("Applied worker override from command.")

                if decision_reasoning or preflight_warnings:
                    before_execution = before_execution + " Memory reasoning: " + " ".join(decision_reasoning)
                    if preflight_warnings:
                        before_execution += " Warnings: " + " ".join(preflight_warnings)

                requires_gate = (
                    _has_non_trivial_adjustments(extra_payload)
                    or run_with_improvement
                    or bool(preflight_warnings)
                )
                if requires_gate and not payload.confirm_execution:
                    prompt = _create_interaction_prompt(
                        interaction_type="execution_confirmation",
                        command=command_text,
                        recommendation="Review and approve these runtime adjustments before execution.",
                        questions=[
                            "Approve execution with these adjustments?",
                            "Any worker override or retry/timeout changes?",
                        ],
                        pending_adjustments=extra_payload,
                        metadata={
                            "workflow_name": selected_workflow,
                            "target_machine_uuid": selected_worker.machine_uuid,
                            "selected_worker_name": selected_worker.machine_name,
                        },
                    )
                    after_execution = "Execution is paused pending approval because non-trivial changes are proposed."
                    suggested_next_action = "Approve the interaction to run with adjustments, or edit them first."
                    requires_confirmation = True
                    pending_interaction_id = str(prompt.get("interaction_id"))
                    pending_questions = list(prompt.get("questions") or [])
                else:
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
                        after_execution += f" Runtime adjustments: {extra_payload}."
                    if run_with_improvement:
                        after_execution += " Run used an approved improvement proposal context."
                    suggested_next_action = "I recommend watching logs and heartbeats while this task runs."
                    _attach_live_reasoning(task.id, decision_reasoning + preflight_warnings)
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
    _record_operational_memory(
        "brain_command",
        f"Intent={recognized_intent} command='{command_text[:120]}'",
        details={
            "command": command_text,
            "recognized_intent": recognized_intent,
            "selected_workflow": selected_workflow,
            "selected_worker": selected_worker.machine_uuid if selected_worker else None,
            "queued_task_id": task.id if task else None,
            "retry_recommended": retry_recommended,
        },
        tags=["brain", recognized_intent],
    )

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
        requires_confirmation=requires_confirmation,
        pending_interaction_id=pending_interaction_id,
        pending_questions=pending_questions,
        live_reasoning=decision_reasoning + preflight_warnings,
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


@app.post("/api/tasks/{task_id}/pause")
def pause_task(task_id: str) -> dict[str, str]:
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    status = str(task.get("status") or "").lower()
    if status in {"completed", "failed", "canceled", "cancelled"}:
        raise HTTPException(status_code=400, detail=f"Task is terminal with status={status}")
    task["status"] = "paused"
    task["updated_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, "Task paused by operator", level="warning")
    return {"status": "paused", "message": f"Task {task.get('id')} paused"}


@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str) -> dict[str, str]:
    task = _find_task_by_ref(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    status = str(task.get("status") or "").lower()
    if status != "paused":
        raise HTTPException(status_code=400, detail=f"Task is not paused (status={status})")
    task["status"] = "queued"
    task["updated_at"] = datetime.utcnow().isoformat()
    _append_task_log(task, "Task resumed and returned to queue")
    return {"status": "queued", "message": f"Task {task.get('id')} resumed"}


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
            if not task.get("started_at"):
                task["started_at"] = datetime.utcnow().isoformat()
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
            reflection = _record_task_outcome_learning(task, outcome="success", machine_uuid=payload.machine_uuid)
            _append_task_log(task, f"Reflection recorded: {reflection.get('id')}")
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
            reflection = _record_task_outcome_learning(
                task,
                outcome="failure",
                machine_uuid=payload.machine_uuid,
                error_text=payload.error,
            )
            _append_task_log(task, f"Reflection recorded: {reflection.get('id')}")
            _create_failure_interaction_if_needed(task, reflection)
            logger.error("Task failed: id=%s machine_uuid=%s error=%s", task_id, payload.machine_uuid, payload.error)
            return {
                "status": "failed",
                "retry_strategy": str(reflection.get("retry_strategy") or "Retry once with focused scope."),
                "alternative_worker": str(reflection.get("alternative_worker") or "none_available"),
                "potential_fix": str(reflection.get("potential_fix") or "Inspect latest worker logs."),
            }

    raise HTTPException(status_code=404, detail="Task not found")
