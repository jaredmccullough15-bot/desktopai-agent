from typing import Any

from pydantic import BaseModel, Field


class WorkerRegisterRequest(BaseModel):
    machine_name: str
    machine_uuid: str
    worker_version: str | None = None
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None


class WorkerUpdateInstruction(BaseModel):
    update_available: bool
    force_update: bool = False
    current_version: str
    latest_version: str | None = None
    package_url: str | None = None
    package_sha256: str | None = None
    message: str | None = None


class WorkerRegisterResponse(BaseModel):
    token: str
    machine_uuid: str
    connection_confirmed: bool = True
    update: WorkerUpdateInstruction | None = None


class WorkerHeartbeatRequest(BaseModel):
    machine_name: str
    machine_uuid: str
    status: str = "idle"
    worker_version: str | None = None
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None


class WorkerUpdateCheckResponse(WorkerUpdateInstruction):
    pass


class TaskCreateRequest(BaseModel):
    task_type: str | None = None
    mode: str | None = None
    url: str | None = None
    selector: str | None = None
    value: str | None = None
    timeout_ms: int | None = None
    name: str | None = None
    steps: list[dict[str, Any]] | None = None
    target_machine_uuid: str | None = None
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

        if self.target_machine_uuid:
            merged_payload["target_machine_uuid"] = self.target_machine_uuid

        return merged_payload


class TaskCreateResponse(BaseModel):
    id: str
    status: str


class ProcedureTemplate(BaseModel):
    name: str
    task_type: str
    description: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ProcedureRunRequest(BaseModel):
    mode: str | None = None
    target_machine_uuid: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowRecord(BaseModel):
    workflow_name: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    login_or_session_required: bool = False
    safe_for_unattended: bool = True
    compatible_worker_types: list[str] = Field(default_factory=lambda: ["any"])
    procedure_name: str | None = None


class BrainCommandRequest(BaseModel):
    command: str
    target_machine_uuid: str | None = None


class BrainCommandResponse(BaseModel):
    recognized_intent: str
    command: str
    before_execution: str
    after_execution: str
    selected_workflow: str | None = None
    selected_worker_uuid: str | None = None
    selected_worker_name: str | None = None
    suggested_next_action: str | None = None
    retry_recommended: bool = False
    task: TaskCreateResponse | None = None


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
