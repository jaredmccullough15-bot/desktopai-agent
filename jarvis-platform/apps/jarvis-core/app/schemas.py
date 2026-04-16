from typing import Any

from pydantic import BaseModel, Field


class WorkerRegisterRequest(BaseModel):
    machine_name: str
    machine_uuid: str
    worker_version: str | None = None
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None


class WorkerRegisterResponse(BaseModel):
    token: str
    machine_uuid: str


class WorkerHeartbeatRequest(BaseModel):
    machine_name: str
    machine_uuid: str
    status: str = "idle"
    worker_version: str | None = None
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None


class TaskCreateRequest(BaseModel):
    task_type: str | None = None
    mode: str | None = None
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    timeout_ms: int | None = None
    name: str | None = None
    steps: list[dict[str, Any]] | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def normalized_payload(self) -> dict[str, Any]:
        merged_payload = dict(self.payload)

        if self.task_type:
            merged_payload["task_type"] = self.task_type

        if self.mode:
            merged_payload["mode"] = self.mode

        if self.url:
            merged_payload["url"] = self.url

        if self.selector:
            merged_payload["selector"] = self.selector

        if self.value is not None:
            merged_payload["value"] = self.value

        if self.timeout_ms is not None:
            merged_payload["timeout_ms"] = self.timeout_ms

        if self.name:
            merged_payload["name"] = self.name

        if self.steps is not None:
            merged_payload["steps"] = self.steps

        return merged_payload


class TaskCreateResponse(BaseModel):
    id: str
    status: str


class TaskCompleteRequest(BaseModel):
    machine_uuid: str
    result_json: dict[str, Any] | None = None


class TaskFailRequest(BaseModel):
    machine_uuid: str
    error: str
    result_json: dict[str, Any] | None = None


class TaskRecord(BaseModel):
    id: str
    payload: dict[str, Any]
    status: str
    assigned_machine_uuid: str | None = None
    result_json: dict[str, Any] | None = None
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    logs: list[dict[str, Any]] = Field(default_factory=list)


class MachineRecord(BaseModel):
    machine_uuid: str
    machine_name: str
    status: str
    worker_version: str | None = None
    last_seen: str | None = None
    online: bool
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None
