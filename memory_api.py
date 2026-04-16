from __future__ import annotations

from fastapi import FastAPI, HTTPException

from models import (
    ConfidenceUpdateIn,
    FailureAnalysisIn,
    MachineOverride,
    RunResultIn,
    SelectorRecord,
    TaskQueueCompleteIn,
    TaskQueueSubmitIn,
    WorkflowRecord,
)
from workflow_store import WorkflowStore


app = FastAPI(title="Jarvis Shared Memory Hub", version="1.0.0")
store = WorkflowStore()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "memory-hub"}


@app.get("/workflow")
def get_workflow(site: str, task_type: str, machine_id: str = "") -> dict:
    workflow = store.get_workflow(site=site, task_type=task_type, machine_id=machine_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="workflow_not_found")
    return workflow


@app.post("/workflow")
def upsert_workflow(workflow: WorkflowRecord) -> dict:
    store.upsert_workflow(workflow)
    return {"ok": True}


@app.get("/selectors")
def get_selectors(site: str, task_type: str, machine_id: str = "", limit: int = 25) -> dict:
    return {"selectors": store.get_selector_memory(site=site, task_type=task_type, machine_id=machine_id, limit=limit)}


@app.post("/selectors/outcome")
def selector_outcome(selector: SelectorRecord, success: bool = True) -> dict:
    store.upsert_selector_memory(selector, success=success)
    return {"ok": True}


@app.post("/run-result")
def submit_run_result(run: RunResultIn) -> dict:
    store.submit_run_result(run)
    return {"ok": True}


@app.post("/failure-analysis")
def submit_failure_analysis(failure: FailureAnalysisIn) -> dict:
    store.submit_failure_analysis(failure)
    return {"ok": True}


@app.get("/machine-overrides/{machine_id}")
def get_machine_overrides(machine_id: str, site: str = "", task_type: str = "") -> dict:
    return {"overrides": store.get_machine_overrides(machine_id=machine_id, site=site, task_type=task_type)}


@app.post("/machine-overrides")
def upsert_machine_override(override: MachineOverride) -> dict:
    store.upsert_machine_override(override)
    return {"ok": True}


@app.post("/confidence/update")
def update_confidence(update: ConfidenceUpdateIn) -> dict:
    store.update_confidence(update)
    return {"ok": True}


@app.post("/tasks")
def enqueue_task(task: TaskQueueSubmitIn) -> dict:
    task_id = store.enqueue_task(task)
    return {"ok": True, "task_id": task_id}


@app.get("/tasks/next")
def claim_next_task(machine_id: str) -> dict:
    task = store.claim_next_task(machine_id=machine_id)
    if not task:
        return {"task": None}
    return {"task": task}


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: int, completion: TaskQueueCompleteIn) -> dict:
    store.complete_task(task_id=task_id, completion=completion)
    return {"ok": True}


@app.get("/tasks/status")
def get_tasks_status(machine_id: str = "", limit: int = 25) -> dict:
    return store.get_task_status(machine_id=machine_id, limit=limit)


# Run with:
#   uvicorn memory_api:app --host 0.0.0.0 --port 8787
