from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


ScopeType = Literal["global", "machine"]


class WorkflowStep(BaseModel):
    step_order: int
    action_type: str
    selector_type: str
    selector_value: str
    wait_condition: str = "visible"
    fallback_hint: str = ""


class WorkflowRecord(BaseModel):
    site: str
    task_type: str
    scope: ScopeType = "global"
    machine_id: str = ""
    version: int = 1
    confidence: float = 0.0
    trusted: bool = False
    steps: list[WorkflowStep] = Field(default_factory=list)


class SelectorRecord(BaseModel):
    site: str
    task_type: str
    action_name: str
    selector_type: str
    selector_value: str
    wait_condition: str = "visible"
    fallback_method: str = ""
    scope: ScopeType = "global"
    machine_id: str = ""
    confidence: float = 0.0
    success_count: int = 0
    failure_count: int = 0


class RunResultIn(BaseModel):
    machine_id: str
    site: str
    task_type: str
    workflow_version: int
    success: bool
    selector_used: dict[str, Any] = Field(default_factory=dict)
    fallback_path: list[str] = Field(default_factory=list)
    screenshot_path: str = ""
    url: str = ""
    title: str = ""
    notes: dict[str, Any] = Field(default_factory=dict)


class FailureAnalysisIn(BaseModel):
    machine_id: str
    site: str
    task_type: str
    failure_type: str
    error_text: str = ""
    screenshot_path: str = ""
    url: str = ""
    title: str = ""
    dom_excerpt: str = ""
    selector_attempts: list[dict[str, str]] = Field(default_factory=list)
    fallback_path: list[str] = Field(default_factory=list)


class MachineOverride(BaseModel):
    machine_id: str
    site: str
    task_type: str
    key: str
    value_json: dict[str, Any] = Field(default_factory=dict)


class ConfidenceUpdateIn(BaseModel):
    site: str
    task_type: str
    scope: ScopeType = "global"
    machine_id: str = ""
    version: Optional[int] = None
    success_delta: int = 0
    failure_delta: int = 0


class TaskRequest(BaseModel):
    machine_id: str
    site: str
    task_type: str
    start_url: str = ""
    goal: str
    input_data: dict[str, Any] = Field(default_factory=dict)


class TaskQueueSubmitIn(BaseModel):
    machine_id: str
    site: str
    task_type: str
    start_url: str = ""
    goal: str
    input_data: dict[str, Any] = Field(default_factory=dict)


class TaskQueueCompleteIn(BaseModel):
    machine_id: str
    success: bool
    result_json: dict[str, Any] = Field(default_factory=dict)
