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
    confirm_execution: bool = False
    interaction_id: str | None = None
    guided_answers: dict[str, Any] = Field(default_factory=dict)
    runtime_adjustments: dict[str, Any] = Field(default_factory=dict)
    run_with_proposal_id: str | None = None


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
    requires_confirmation: bool = False
    pending_interaction_id: str | None = None
    pending_questions: list[str] = Field(default_factory=list)
    live_reasoning: list[str] = Field(default_factory=list)
    task: TaskCreateResponse | None = None


class InteractivePromptRecord(BaseModel):
    interaction_id: str
    created_at: str
    interaction_type: str
    command: str
    workflow_name: str | None = None
    task_id: str | None = None
    status: str = "pending"
    recommendation: str
    questions: list[str] = Field(default_factory=list)
    pending_adjustments: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractivePromptDecisionRequest(BaseModel):
    approved: bool
    adjustments: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class GuidedExecutionStartRequest(BaseModel):
    workflow_name: str
    target_machine_uuid: str | None = None
    initial_answers: dict[str, Any] = Field(default_factory=dict)


class GuidedExecutionAnswerRequest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    continue_execution: bool = True


class RunWithImprovementRequest(BaseModel):
    target_machine_uuid: str | None = None
    confirm_execution: bool = False
    runtime_adjustments: dict[str, Any] = Field(default_factory=dict)


class ConversationPreferenceRecord(BaseModel):
    key: str
    value: Any
    updated_at: str


class ConversationPreferenceUpdateRequest(BaseModel):
    key: str
    value: Any


class OperationalMemoryRecord(BaseModel):
    id: str
    timestamp: str
    kind: str
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class HumanExplanation(BaseModel):
    what_happened: str = ""
    likely_cause: str = ""
    meaning: str = ""
    recommended_next_action: str = ""
    category: str = "unknown"
    memory_hint: str | None = None


class TaskReflectionRecord(BaseModel):
    id: str
    timestamp: str
    task_id: str
    workflow_name: str | None = None
    worker_name: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    status: str = "unknown"
    failure_stage: str | None = None
    failure_classification: str | None = None
    likely_root_cause: str = "unknown"
    supporting_evidence: str = ""
    recommended_next_action: str = ""
    retry_strategy: str | None = None
    alternative_worker: str | None = None
    potential_fix: str | None = None
    recommendation_feedback: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    # Human-readable explanation layer
    human_summary: str | None = None
    human_explanation: HumanExplanation | None = None


class ImprovementProposalRecord(BaseModel):
    proposal_id: str
    created_at: str
    workflow_name: str
    worker_name: str | None = None
    proposal_type: str
    title: str
    description: str
    supporting_evidence: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    recommended_change: str
    status: str = "open"
    feedback: list[str] = Field(default_factory=list)


class ProposalStatusUpdateRequest(BaseModel):
    status: str


class ProposalFeedbackRequest(BaseModel):
    feedback: str


class WorkflowSOPSummaryRecord(BaseModel):
    workflow_name: str
    purpose: str
    prerequisites: list[str] = Field(default_factory=list)
    normal_flow: list[str] = Field(default_factory=list)
    common_failures: list[str] = Field(default_factory=list)
    recommended_fixes: list[str] = Field(default_factory=list)
    best_worker_patterns: list[str] = Field(default_factory=list)
    updated_at: str


class WorkflowSOPUpdateRequest(BaseModel):
    purpose: str | None = None
    prerequisites: list[str] | None = None
    normal_flow: list[str] | None = None
    common_failures: list[str] | None = None
    recommended_fixes: list[str] | None = None
    best_worker_patterns: list[str] | None = None


class WorkflowVariableDefinition(BaseModel):
    """Top-level variable registry entry for a workflow draft."""
    field_key: str
    label: str = ""
    is_variable: bool = True
    # source: user_input | derived | constant
    source: str = "user_input"
    default_value: str = ""
    prompt_question: str = ""
    example_value: str = ""


class WorkflowStepValidation(BaseModel):
    """Validation contract for a single workflow step."""
    success_condition: str = ""
    failure_condition: str = ""
    recovery_strategy: str = ""


class WorkflowLearningCreateRequest(BaseModel):
    learning_path: str
    source_text: str | None = None
    workflow_name: str | None = None
    goal: str | None = None


class WorkflowLearningDraftRecord(BaseModel):
    draft_id: str
    created_at: str
    updated_at: str
    learning_path: str
    workflow_name: str
    goal: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    required_session_state: list[str] = Field(default_factory=list)
    safe_for_unattended: bool = False
    steps: list[dict[str, Any]] = Field(default_factory=list)
    # Top-level variable registry (promoted from per-step variable_inputs)
    variables: list[dict[str, Any]] = Field(default_factory=list)
    validation_rules: list[str] = Field(default_factory=list)
    fallback_strategies: list[str] = Field(default_factory=list)
    common_failures: list[str] = Field(default_factory=list)
    review_status: str = "draft"
    reviewer_notes: str | None = None
    published_workflow_name: str | None = None
    # Teaching loop state
    teaching_complete: bool = False
    teaching_pending_step: int | None = None


class WorkflowDraftStatusUpdateRequest(BaseModel):
    review_status: str
    reviewer_notes: str | None = None


class WorkflowDraftTestRequest(BaseModel):
    target_machine_uuid: str | None = None
    guided_mode: bool = True
    runtime_adjustments: dict[str, Any] = Field(default_factory=dict)


class WorkflowDraftPublishRequest(BaseModel):
    approved_by: str | None = None
    publish_notes: str | None = None


class WorkflowDraftStructureUpdateRequest(BaseModel):
    steps: list[dict[str, Any]] | None = None
    required_inputs: list[str] | None = None
    validation_rules: list[str] | None = None
    fallback_strategies: list[str] | None = None
    common_failures: list[str] | None = None
    variables: list[dict[str, Any]] | None = None


class TeachingStepQuestion(BaseModel):
    """A single question asked during the interactive teaching loop."""
    step_order: int
    field: str
    question: str
    current_value: str | None = None
    options: list[str] = Field(default_factory=list)


class TeachingSessionQuestion(BaseModel):
    """Teaching loop response: next step that needs clarification."""
    draft_id: str
    step_order: int
    step_name: str
    questions: list[TeachingStepQuestion] = Field(default_factory=list)
    teaching_complete: bool = False
    steps_remaining: int = 0


class TeachingStepAnswerItem(BaseModel):
    field: str
    value: str


class TeachingSessionAnswerRequest(BaseModel):
    """Submit answers for one step's teaching questions."""
    step_order: int
    answers: list[TeachingStepAnswerItem] = Field(default_factory=list)


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
