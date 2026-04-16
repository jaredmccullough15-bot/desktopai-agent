import logging
from datetime import datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    MachineRecord,
    TaskCompleteRequest,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskFailRequest,
    TaskRecord,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerRegisterResponse,
)

app = FastAPI(title="bill-core", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bill-core")

registered_workers: dict[str, dict] = {}
tasks: list[dict] = []


def _append_task_log(task: dict, message: str, level: str = "info") -> None:
    logs = task.setdefault("logs", [])
    logs.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "message": message,
        }
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": "0.1.0"}


@app.post("/worker/register", response_model=WorkerRegisterResponse)
def register_worker(payload: WorkerRegisterRequest) -> WorkerRegisterResponse:
    token = f"mock-token-{payload.machine_uuid[:8]}"
    registered_workers[payload.machine_uuid] = {
        "machine_name": payload.machine_name,
        "token": token,
        "last_seen": datetime.utcnow().isoformat(),
        "status": "idle",
        "worker_version": payload.worker_version or "unknown",
        "execution_mode": payload.execution_mode or "headless_background",
        "current_task_id": payload.current_task_id,
        "current_step": payload.current_step,
    }
    logger.info("Worker registered: name=%s uuid=%s", payload.machine_name, payload.machine_uuid)
    return WorkerRegisterResponse(token=token, machine_uuid=payload.machine_uuid)


@app.post("/worker/heartbeat")
def worker_heartbeat(payload: WorkerHeartbeatRequest) -> dict[str, str]:
    worker = registered_workers.setdefault(
        payload.machine_uuid,
        {
            "machine_name": payload.machine_name,
            "token": "unregistered",
            "status": payload.status,
            "last_seen": datetime.utcnow().isoformat(),
            "worker_version": payload.worker_version or "unknown",
            "execution_mode": payload.execution_mode or "headless_background",
            "current_task_id": payload.current_task_id,
            "current_step": payload.current_step,
        },
    )
    worker["status"] = payload.status
    worker["last_seen"] = datetime.utcnow().isoformat()
    if payload.worker_version:
        worker["worker_version"] = payload.worker_version
    if payload.execution_mode:
        worker["execution_mode"] = payload.execution_mode
    worker["current_task_id"] = payload.current_task_id
    worker["current_step"] = payload.current_step
    logger.info("Heartbeat: name=%s uuid=%s status=%s", payload.machine_name, payload.machine_uuid, payload.status)
    return {"status": "ok"}


@app.post("/api/tasks", response_model=TaskCreateResponse)
async def create_task(payload: TaskCreateRequest, request: Request) -> TaskCreateResponse:
    task_id = str(uuid4())
    normalized_payload = payload.normalized_payload()

    raw_body = await request.json()
    if isinstance(raw_body, dict) and raw_body.get("mode") and "mode" not in normalized_payload:
        normalized_payload["mode"] = raw_body["mode"]

    tasks.append(
        {
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
    )
    _append_task_log(tasks[-1], f"Task created with type={normalized_payload.get('task_type', 'unknown')}")
    logger.info("Task created: id=%s task_type=%s", task_id, normalized_payload.get("task_type", "unknown"))
    return TaskCreateResponse(id=task_id, status="queued")


@app.get("/api/machines", response_model=list[MachineRecord])
def list_machines() -> list[MachineRecord]:
    now = datetime.utcnow()
    machines: list[MachineRecord] = []

    for machine_uuid, worker in registered_workers.items():
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

    return machines


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


@app.get("/worker/tasks/next", response_model=TaskRecord | None)
def get_next_task(machine_uuid: str):
    if machine_uuid not in registered_workers:
        raise HTTPException(status_code=400, detail="Worker not registered")

    for task in tasks:
        if task["status"] == "queued":
            task["status"] = "assigned"
            task["assigned_machine_uuid"] = machine_uuid
            task["updated_at"] = datetime.utcnow().isoformat()
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
