from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas import TaskCreateResponse


class AuditClientContext(BaseModel):
    client_name: str
    external_contact_id: str
    policy_number: str
    marketplace_id: str


class AuditSourceRecord(BaseModel):
    source_system: str
    client_name: str
    external_contact_id: str
    policy_number: str
    marketplace_id: str
    raw: dict[str, Any] = Field(default_factory=dict)


class AuditTargetContact(BaseModel):
    target_system: str
    client_name: str
    external_contact_id: str
    policy_number: str
    marketplace_id: str
    agent_of_record: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AuditDecisionContext(BaseModel):
    audit_status: str
    agent_of_record: bool | None = None
    identity_score: int | None = None
    selected_rule: str | None = None
    selected_action: str | None = None
    dry_run: bool = False
    requires_human_approval: bool = False
    audit_context: dict[str, Any] = Field(default_factory=dict)


class TenantWorkflowTaskContext(BaseModel):
    tenant_id: str
    workflow_id: str
    task_id: str | None = None
    source_system: str
    target_system: str
    client_name: str
    external_contact_id: str
    policy_number: str
    marketplace_id: str
    audit_status: str
    agent_of_record: bool | None = None
    identity_score: int | None = None
    selected_rule: str | None = None
    selected_action: str | None = None
    dry_run: bool = False
    requires_human_approval: bool = False
    target_machine_uuid: str | None = None
    mode: str | None = None
    debug_metadata: dict[str, Any] = Field(default_factory=dict)


class AuditActionResult(BaseModel):
    selected_rule: str | None = None
    selected_action: str | None = None
    action_steps_count: int = 0
    dry_run: bool = False
    requires_human_approval: bool = False


class TenantWorkflowRunRequest(BaseModel):
    tenant_id: str
    workflow_id: str
    source_system: str
    target_system: str
    client_name: str
    external_contact_id: str
    policy_number: str
    marketplace_id: str
    audit_status: str
    agent_of_record: bool | None = None
    dry_run: bool = False
    requires_human_approval: bool = False
    mode: str = "interactive_visible"
    target_machine_uuid: str | None = None
    source_record: AuditSourceRecord
    target_contact: AuditTargetContact
    decision_context: AuditDecisionContext
    debug_metadata: dict[str, Any] = Field(default_factory=dict)


class TenantWorkflowRunResult(BaseModel):
    tenant_id: str
    workflow_id: str
    task_id: str
    identity_score: int
    selected_rule: str | None = None
    selected_action: str | None = None
    dry_run: bool = False
    requires_human_approval: bool = False
    queued_task: TaskCreateResponse
    task_context: TenantWorkflowTaskContext
    action_result: AuditActionResult