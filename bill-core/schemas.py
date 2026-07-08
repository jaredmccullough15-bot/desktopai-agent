from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkerRegisterRequest(BaseModel):
    machine_name: str
    machine_uuid: str
    tenant_id: str | None = None
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
    updater_script_url: str | None = None
    message: str | None = None


class WorkerRegisterResponse(BaseModel):
    token: str
    machine_uuid: str
    connection_confirmed: bool = True
    update: WorkerUpdateInstruction | None = None


class WorkerHeartbeatRequest(BaseModel):
    machine_name: str
    machine_uuid: str
    tenant_id: str | None = None
    status: str = "idle"
    worker_version: str | None = None
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None
    update_status: str | None = None
    update_target_version: str | None = None
    update_error: str | None = None


class WorkerUpdateCheckResponse(WorkerUpdateInstruction):
    pass


class WorkerReleaseRecord(BaseModel):
    id: str
    version: str
    upload_time: str
    release_notes: str | None = None
    package_filename: str
    package_sha256: str | None = None
    is_active: bool = False
    channel: str = "optional"


# ---------------------------------------------------------------------------
# Worker Download Center schemas
# ---------------------------------------------------------------------------

class WorkerReleasePublicRecord(BaseModel):
    """Metadata returned to authorized users for the download center UI."""
    id: str
    version: str
    upload_time: str
    release_notes: str | None = None
    package_filename: str
    package_sha256: str | None = None
    file_size_bytes: int | None = None
    status: str = "current"  # current | draft | deprecated | disabled
    released_by_name: str | None = None
    download_count: int = 0


class WorkerReleaseAdminRecord(WorkerReleasePublicRecord):
    """Extended metadata for admin-only release list."""
    released_by_user_id: str | None = None
    channel: str = "stable"


class WorkerReleaseCreateRequest(BaseModel):
    version: str
    package_filename: str
    release_notes: str | None = None
    channel: str = "stable"


class WorkerReleaseMarkCurrentRequest(BaseModel):
    confirm: bool = True


class WorkerReleaseDisableRequest(BaseModel):
    confirm: bool = True


class WorkerDownloadUrlResponse(BaseModel):
    release_id: str
    version: str
    package_filename: str
    download_url: str
    sha256: str | None = None
    expires_in_seconds: int | None = None


class ExtensionDownloadUrlResponse(BaseModel):
    release_id: str
    version_label: str
    file_name: str
    download_url: str
    sha256_hash: str | None = None
    expires_in_seconds: int | None = None


# ---------------------------------------------------------------------------
# Chrome Extension Download Center schemas
# ---------------------------------------------------------------------------

class ExtensionReleasePublicRecord(BaseModel):
    id: str
    release_type: str = "chrome_extension"
    version_label: str
    released_at: str
    release_notes: str | None = None
    file_name: str
    sha256_hash: str | None = None
    file_size_bytes: int | None = None
    status: str = "current"  # current | draft | deprecated | disabled
    released_by_name: str | None = None
    download_count: int = 0


class ExtensionReleaseAdminRecord(ExtensionReleasePublicRecord):
    released_by_user_id: str | None = None


class ExtensionReleaseCreateRequest(BaseModel):
    version_label: str
    file_name: str
    release_notes: str | None = None


class ExtensionReleaseMarkCurrentRequest(BaseModel):
    confirm: bool = True


class ExtensionReleaseDisableRequest(BaseModel):
    confirm: bool = True


class WorkerDeployRequest(BaseModel):
    machine_uuids: list[str] | None = None
    force: bool = False
    idle_only: bool = False


class WorkerDeployResponse(BaseModel):
    queued: list[str]
    skipped: list[str]
    message: str


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


class BatchRunRowRecord(BaseModel):
    row_id: str
    row_number: int
    source: dict[str, str] = Field(default_factory=dict)
    mapped: dict[str, str] = Field(default_factory=dict)
    required_missing: list[str] = Field(default_factory=list)
    status: str
    payment_status: Literal["good", "bad", "needs_review"]
    decision_reason: str
    paid_through_date: str | None = None
    current_month_end_date: str | None = None
    child_task_id: str | None = None
    task_id: str | None = None
    child_task_status: str | None = None
    assigned_machine_uuid: str | None = None
    worker_name: str | None = None
    matched_client_name: str | None = None
    keap_task_created: bool = False
    keap_task_id: str | None = None
    notes: str | None = None
    error: str | None = None
    row_started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str
    workflow_name: str
    target_machine_uuid: str
    tenant_id: str


class BatchRunSummaryRecord(BaseModel):
    total: int = 0
    ready: int = 0
    invalid: int = 0
    queued: int = 0
    assigned: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0
    canceled: int = 0
    needs_review: int = 0
    total_rows: int = 0
    pending_rows: int = 0
    running_rows: int = 0
    completed_rows: int = 0
    failed_rows: int = 0
    needs_review_rows: int = 0
    skipped_rows: int = 0
    canceled_rows: int = 0
    good_no_action_needed_rows: int = 0
    bad_payment_task_created_rows: int = 0
    progress_percent: int = 0
    estimated_remaining_seconds: int | None = None


class BatchRunRecord(BaseModel):
    batch_id: str
    tenant_id: str
    workflow_name: str
    target_machine_uuid: str
    target_worker_name: str | None = None
    status: str
    filename: str
    headers: list[str] = Field(default_factory=list)
    mapping: dict[str, str] = Field(default_factory=dict)
    parser_meta: dict[str, Any] = Field(default_factory=dict)
    rows: list[BatchRunRowRecord] = Field(default_factory=list)
    summary: BatchRunSummaryRecord = Field(default_factory=BatchRunSummaryRecord)
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    cancel_requested: bool = False


class BatchRunUploadResponse(BaseModel):
    batch: BatchRunRecord
    mapping_validation: dict[str, Any] = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)


class BatchRunRowsResponse(BaseModel):
    batch_id: str
    total_rows: int
    rows: list[BatchRunRowRecord] = Field(default_factory=list)
    summary: BatchRunSummaryRecord = Field(default_factory=BatchRunSummaryRecord)


class BatchRunStartResponse(BaseModel):
    batch_id: str
    status: str
    queued_rows: int = 0
    skipped_rows: int = 0
    summary: BatchRunSummaryRecord = Field(default_factory=BatchRunSummaryRecord)


class BatchRunCancelResponse(BaseModel):
    batch_id: str
    status: str
    cancel_requested: bool = True


class BatchRunRetryResponse(BaseModel):
    batch_id: str
    status: str
    retried_rows: int = 0
    summary: BatchRunSummaryRecord = Field(default_factory=BatchRunSummaryRecord)


class BatchRunListResponse(BaseModel):
    items: list[BatchRunRecord] = Field(default_factory=list)
    count: int = 0


class WorkflowTimeoutPolicy(BaseModel):
    """Per-workflow timeout recovery policy. All fields are optional — defaults apply."""
    max_step_retries: int = 2
    max_recovery_attempts: int = 3
    restart_allowed: bool = True
    prefer_human_escalation: bool = False
    step_timeout_ms: int = 20000
    page_timeout_ms: int = 45000
    checkpoint_after_n_steps: int = 5


class WorkflowRecord(BaseModel):
    workflow_name: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    login_or_session_required: bool = False
    safe_for_unattended: bool = True
    compatible_worker_types: list[str] = Field(default_factory=lambda: ["any"])
    procedure_name: str | None = None
    timeout_policy: WorkflowTimeoutPolicy | None = None
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    last_updated_by_user_id: str | None = None
    last_updated_by_name: str | None = None
    approved_by_user_id: str | None = None
    approved_by_name: str | None = None


class BrainCommandRequest(BaseModel):
    command: str
    target_machine_uuid: str | None = None
    confirm_execution: bool = False
    interaction_id: str | None = None
    guided_answers: dict[str, Any] = Field(default_factory=dict)
    runtime_adjustments: dict[str, Any] = Field(default_factory=dict)
    run_with_proposal_id: str | None = None


class TeachingStartupState(BaseModel):
    """Returned inside BrainCommandResponse when a teach_session task is queued.

    The frontend uses this to:
    - Show a teaching startup overlay immediately (before the browser opens)
    - Poll GET /api/teaching/session/{session_id}/status every 2 s until active/failed
    """
    session_id: str
    task_id: str | None = None
    workflow_name: str
    target_machine_uuid: str | None = None
    target_machine_name: str | None = None
    status: str = "browser_opening"  # browser_opening | active | failed
    message: str = ""
    overlay_enabled: bool = True
    voice_prompt_text: str = "Teaching mode is starting. Once the browser opens, tell me what this workflow does."
    teaching_session: "TeachingSession | None" = None
    copilot_notice: str | None = None
    copilot_interpretation: str | None = None
    copilot_question: str | None = None


class TeachingStartupStatusRequest(BaseModel):
    """Worker calls POST /api/teaching/session/{session_id}/status with this body."""
    status: str  # active | failed
    task_id: str | None = None
    message: str = ""


class BrowserAction(BaseModel):
    id: str
    type: Literal["click", "type", "navigate", "select", "submit"]
    source: Literal["browser", "extension", "manual"] | None = None
    selector: str | None = None
    selectors: list[str] = Field(default_factory=list)
    locator_candidates: list[dict[str, Any]] = Field(default_factory=list)
    label: str | None = None
    target_label: str | None = None
    target_type: str | None = None
    descriptors: list[str] = Field(default_factory=list)
    value_redacted: str | None = None
    url: str | None = None
    timestamp: str


class TeachingSessionActionRequest(BaseModel):
    action: BrowserAction
    step_id: str | None = None
    page_context: dict | None = None         # raw PageContextSnapshot from browser


class TeachingExtensionEventElement(BaseModel):
    target_type: str | None = None
    target_label: str | None = None
    visible_text: str | None = None
    role: str | None = None
    aria_label: str | None = None
    placeholder: str | None = None
    name: str | None = None
    element_id: str | None = None
    nearby_label_text: str | None = None
    bounding_box: dict[str, Any] | None = None
    selector_candidates: list[str] = Field(default_factory=list)
    selectors: list[str] = Field(default_factory=list)
    is_sensitive: bool = False


class TeachingExtensionEventRequest(BaseModel):
    event_type: Literal["context", "click", "focus", "input", "change", "submit"]
    current_url: str | None = None
    page_title: str | None = None
    domain: str | None = None
    visible_buttons: list[dict[str, Any]] = Field(default_factory=list)
    visible_fields: list[dict[str, Any]] = Field(default_factory=list)
    visible_links: list[dict[str, Any]] = Field(default_factory=list)
    visible_headings: list[dict[str, Any]] = Field(default_factory=list)
    active_element: dict[str, Any] | None = None
    target: TeachingExtensionEventElement | None = None
    input_metadata: dict[str, Any] | None = None
    page_changed: bool = False
    paired_session_code: str | None = None
    captured_at: str | None = None
    source: str = "extension"


class WorkflowStep(BaseModel):
    id: str
    order: int
    title: str
    observed_actions: list[BrowserAction] = Field(default_factory=list)
    employee_explanation: str | None = None
    bill_summary: str = ""
    bill_confidence: float = 0.0
    pending_question: str | None = None
    reasoning_reason: str | None = None
    needs_reasoning: bool = False
    unanswered_question: bool = False
    last_reasoned_at: str | None = None
    decision_rules: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    confirmed: bool = False


class TeachingSession(BaseModel):
    session_id: str
    workflow_name: str
    workflow_summary: str | None = None
    status: Literal["intro", "teaching", "review", "approved"] = "intro"
    start_url: str | None = None
    observed_start_url: str | None = None
    suggested_start_url: str | None = None
    observed_current_page: str | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)
    page_context_snapshot: dict | None = None  # last captured PageContextSnapshot
    page_context_history: list[dict] = Field(default_factory=list)
    extension_connection_status: str | None = None
    extension_event_count: int = 0
    last_extension_event: dict[str, Any] | None = None
    extension_events: list[dict[str, Any]] = Field(default_factory=list)


class BillUserRecord(BaseModel):
    id: str
    tenant_id: str | None = None
    email: str
    name: str
    role: Literal["super_admin", "admin", "teacher", "runner", "viewer"] = "viewer"
    status: str = "active"
    last_login_at: str | None = None
    created_at: str
    updated_at: str


class BillLoginRequest(BaseModel):
    email: str
    password: str


class BillLoginResponse(BaseModel):
    user: BillUserRecord
    session_expires_at: str


class BillCurrentUserResponse(BaseModel):
    user: BillUserRecord


class BillCreateUserRequest(BaseModel):
    name: str
    email: str
    password: str
    role: Literal["super_admin", "admin", "teacher", "runner", "viewer"] = "viewer"
    status: str = "active"
    tenant_id: str | None = None


class BillUpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    password: str | None = None
    role: Literal["super_admin", "admin", "teacher", "runner", "viewer"] | None = None
    status: str | None = None


class BillAuditLogRecord(BaseModel):
    id: int
    tenant_id: str | None = None
    event_type: str
    actor_user_id: str | None = None
    actor_user_name: str | None = None
    actor_role: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    redacted_payload: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    created_at: str


class KnowledgeRecord(BaseModel):
    knowledge_id: str
    title: str
    category: str
    applies_to: list[str] = Field(default_factory=list)
    content: str
    source_type: Literal["manual", "document", "imported", "system"] = "manual"
    tags: list[str] = Field(default_factory=list)
    status: Literal["active", "draft", "archived"] = "draft"
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    created_at: str
    updated_at: str
    version: int = 1
    tenant_id: str | None = None
    copied_from_tenant_id: str | None = None
    copied_from_record_id: str | None = None
    copied_by_user_id: str | None = None
    copied_at: str | None = None


class KnowledgeCreateRequest(BaseModel):
    title: str
    category: str
    applies_to: list[str] = Field(default_factory=list)
    content: str
    source_type: Literal["manual", "document", "imported", "system"] = "manual"
    tags: list[str] = Field(default_factory=list)
    status: Literal["active", "draft", "archived"] = "draft"
    tenant_id: str | None = None


class KnowledgeUpdateRequest(BaseModel):
    title: str | None = None
    category: str | None = None
    applies_to: list[str] | None = None
    content: str | None = None
    source_type: Literal["manual", "document", "imported", "system"] | None = None
    tags: list[str] | None = None
    status: Literal["active", "draft", "archived"] | None = None
    tenant_id: str | None = None


class SuperAdminTenantRecord(BaseModel):
    tenant_id: str
    name: str
    status: Literal["active", "suspended"] = "active"
    contact_email: str | None = None
    notes: str | None = None
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class SuperAdminTenantCreateRequest(BaseModel):
    tenant_id: str
    name: str
    contact_email: str | None = None
    notes: str | None = None


class SuperAdminTenantUpdateRequest(BaseModel):
    name: str | None = None
    contact_email: str | None = None
    notes: str | None = None
    settings: dict[str, Any] | None = None
    status: Literal["active", "suspended"] | None = None


class SuperAdminCopyKnowledgeRequest(BaseModel):
    source_tenant_id: str
    source_knowledge_id: str
    target_tenant_id: str
    activate: bool = False


class SuperAdminCopyWorkflowRequest(BaseModel):
    source_tenant_id: str
    source_workflow_id: str
    target_tenant_id: str
    activate: bool = False


class IntegrationCredentialRecord(BaseModel):
    integration_id: str
    tenant_id: str
    integration_type: str
    name: str
    status: str = "active"
    settings: dict[str, Any] = Field(default_factory=dict)
    secret_masked: str
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    updated_by_user_id: str | None = None
    updated_by_name: str | None = None
    created_at: str
    updated_at: str


class IntegrationCredentialCreateRequest(BaseModel):
    integration_type: str
    name: str
    secret: str
    status: str = "active"
    settings: dict[str, Any] = Field(default_factory=dict)


class IntegrationCredentialUpdateRequest(BaseModel):
    name: str | None = None
    secret: str | None = None
    status: str | None = None
    settings: dict[str, Any] | None = None


class TeachingSessionMessageRequest(BaseModel):
    message: str
    step_id: str | None = None


class TeachingSessionMessageResponse(BaseModel):
    reply: str
    teaching_session: TeachingSession
    copilot_notice: str | None = None        # "I saw you …"
    copilot_interpretation: str | None = None  # "I think this …"
    copilot_question: str | None = None      # "Bill's question"


class TeachingReasoningRequest(BaseModel):
    step_id: str | None = None
    latest_employee_message: str | None = None


class TeachingReasoningResponse(BaseModel):
    bill_summary: str
    suggested_step_title: str
    question: str
    confidence: float
    should_interrupt: bool
    reason: str
    step_id: str | None = None
    step_order: int | None = None


class TeachingSessionReviewStepSummary(BaseModel):
    step_id: str
    order: int
    title: str
    confirmed: bool
    bill_summary: str = ""
    employee_explanation: str | None = None
    observed_actions: list[BrowserAction] = Field(default_factory=list)
    decision_rules: list[str] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)


class TeachingSessionReviewSummary(BaseModel):
    workflow_summary: str = ""
    total_steps: int = 0
    confirmed_steps: int = 0
    unconfirmed_steps: int = 0
    steps: list[TeachingSessionReviewStepSummary] = Field(default_factory=list)


class TeachingSessionReviewResponse(BaseModel):
    reply: str
    teaching_session: TeachingSession
    review_summary: TeachingSessionReviewSummary
    warnings: list[str] = Field(default_factory=list)
    draft_result: dict[str, Any] | None = None
    execution_readiness: dict[str, Any] | None = None


class BrainCommandResponse(BaseModel):
    recognized_intent: str
    command: str
    before_execution: str
    after_execution: str
    reply: str | None = None
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
    speak_response: bool = False
    voice_text: str | None = None
    suggested_emotion: str | None = None
    suggested_style_profile: str | None = None
    voice_event_type: str | None = None
    teaching_mode: TeachingStartupState | None = None
    teaching_session: TeachingSession | None = None  # Apprentice-mode session included at creation


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
    # Timeout-specific recovery fields (populated when failure_classification == "timeout")
    timeout_type: str | None = None
    timeout_recovery_attempts: int | None = None
    timeout_recovery_log: list[dict[str, Any]] | None = None
    timeout_restart_attempted: bool | None = None
    timeout_narrative: str | None = None
    timeout_policy_applied: dict[str, Any] | None = None


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


class WorkflowGeneratedSOPRecord(BaseModel):
    workflow_id: str
    draft_id: str
    workflow_name: str
    readiness_status: Literal["runnable", "needs_more_teaching", "manual_only"] = "needs_more_teaching"
    runnable: bool = False
    has_start_url: bool = False
    last_validated_date: str | None = None
    generated_at: str
    markdown: str
    source_summary: dict[str, Any] = Field(default_factory=dict)


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


class WorkflowExecutionReadiness(BaseModel):
    executable: bool = False
    runnable: bool = False
    has_start_url: bool = False
    start_url: str | None = None
    executable_action_count: int = 0
    manual_action_count: int = 0
    redacted_input_count: int = 0
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class WorkflowLearningDraftRecord(BaseModel):
    draft_id: str
    tenant_id: str | None = None
    created_at: str
    updated_at: str
    learning_path: str
    workflow_name: str
    goal: str
    description: str
    required_inputs: list[str] = Field(default_factory=list)
    identity_required: bool = False
    identity_fields: list[str] = Field(default_factory=list)
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
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    created_by_role: str | None = None
    last_updated_by_user_id: str | None = None
    last_updated_by_name: str | None = None
    last_updated_by_role: str | None = None
    approved_by_user_id: str | None = None
    approved_by_name: str | None = None
    published_by_user_id: str | None = None
    published_by_name: str | None = None
    observation_question_frequency: Literal["low", "medium", "high"] = "medium"
    observation_questions_paused: bool = False
    observation_skip_all_questions: bool = False
    rule_suggestions: list[dict[str, Any]] = Field(default_factory=list)
    workflow_annotations: list[dict[str, Any]] = Field(default_factory=list)
    training_memory: list[dict[str, Any]] = Field(default_factory=list)
    navigation_rules: list[dict[str, Any]] = Field(default_factory=list)
    execution_readiness: WorkflowExecutionReadiness = Field(default_factory=WorkflowExecutionReadiness)
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
    identity_required: bool | None = None
    identity_fields: list[str] | None = None
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


class AppendStepRequest(BaseModel):
    """A single observed browser action to append to a workflow draft."""
    action: str
    selector: str = ""
    url: str = ""
    value: str = ""
    option: str = ""
    created_by_user_id: str | None = None
    created_by_name: str | None = None
    created_at: str | None = None
    taught_by_user_id: str | None = None
    taught_by_name: str | None = None
    taught_at: str | None = None
    last_updated_by_user_id: str | None = None
    last_updated_by_name: str | None = None
    last_updated_at: str | None = None
    captured_by_user_id: str | None = None
    captured_by_name: str | None = None
    captured_at: str | None = None
    step_name: str = ""
    intent: str = ""
    description: str = ""
    element_label: str = ""
    element_tag: str = ""
    element_type: str = ""
    captured_at: str = ""
    event_type: str = ""
    system_context: dict[str, Any] = Field(default_factory=dict)
    observation_triggers: list[str] = Field(default_factory=list)


class ObservationQuestionPrompt(BaseModel):
    prompt_id: str
    draft_id: str
    step_order: int
    trigger_type: Literal[
        "system_switch",
        "decision_point",
        "classification_step",
        "unknown_pattern",
        "system_selection",
        "domain_navigation",
        "navigation_decision",
    ]
    question_type: Literal[
        "check",
        "decision",
        "classification",
        "why_action",
        "navigation_why",
        "navigation_which",
        "navigation_source",
        "navigation_rule",
    ]
    question: str
    system_context: dict[str, Any] = Field(default_factory=dict)
    status: Literal["pending", "answered", "skipped", "later", "known"] = "pending"
    can_skip: bool = True
    can_answer_later: bool = True
    voice_supported: bool = True


class ObservationQuestionAnswerRequest(BaseModel):
    prompt_id: str
    step_order: int
    action: Literal["answer", "skip", "later", "known", "pause", "resume", "skip_all", "set_frequency"] = "answer"
    answer: str = ""
    response_mode: Literal["text", "voice", "control"] = "text"
    question_type: str | None = None
    trigger_type: str | None = None
    question_frequency: Literal["low", "medium", "high"] | None = None
    system_context: dict[str, Any] = Field(default_factory=dict)


class ObservationQuestionAnswerResponse(BaseModel):
    draft_id: str
    step_order: int
    prompt_id: str
    status: str
    saved_answer: bool = False
    observation_question_frequency: Literal["low", "medium", "high"] = "medium"
    observation_questions_paused: bool = False
    observation_skip_all_questions: bool = False
    generated_rule_candidate: dict[str, Any] | None = None


class NavigationMapping(BaseModel):
    """Single field → system mapping rule."""
    mapping_id: str
    source_field: str
    source_value: str
    target_system: str
    target_url_pattern: str = ""
    confidence: float = 1.0
    learned_from_answers: int = 1
    is_rule_always: bool = True
    captured_at: str
    updated_at: str


class NavigationRule(BaseModel):
    """A learned navigation path: how to choose a system and reach it."""
    rule_id: str
    draft_id: str
    step_order: int
    trigger_type: Literal["system_selection", "domain_navigation", "navigation_decision"]
    question_type: Literal["navigation_why", "navigation_which", "navigation_source", "navigation_rule"]
    condition: str
    current_system: str = ""
    target_system: str
    target_url_pattern: str = ""
    system_context: dict[str, Any] = Field(default_factory=dict)
    mappings: list[NavigationMapping] = Field(default_factory=list)
    answer: str
    response_mode: str = "text"
    status: str = "candidate"
    source: str = "interactive_observation"
    captured_at: str
    updated_at: str


class NavigationRuleMapping(BaseModel):
    """Multi-tenant navigation mapping store."""
    tenant_id: str
    workflow_id: str | None = None
    navigation_rules: list[NavigationRule] = Field(default_factory=list)
    missing_mappings_warnings: list[str] = Field(default_factory=list)
    applied_rules_count: int = 0
    created_at: str
    updated_at: str


class TeachSessionStartRequest(BaseModel):
    """Request body to launch a Playwright teach session from the dashboard."""
    start_url: str = ""
    api_base: str = ""
    target_machine_uuid: str = ""  # When set, queues task to that worker instead of spawning locally


class TaskCompleteRequest(BaseModel):
    machine_uuid: str
    result_json: dict[str, Any] | None = None


class TaskFailRequest(BaseModel):
    machine_uuid: str
    error: str
    result_json: dict[str, Any] | None = None
    # Optional step context for richer timeout classification
    step_name: str | None = None
    step_index: int | None = None
    recovery_context: dict[str, Any] | None = None


class TaskRecord(BaseModel):
    id: str
    tenant_id: str | None = None
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
    tenant_id: str | None = None
    status: str
    worker_version: str | None = None
    last_seen: str | None = None
    online: bool
    execution_mode: str | None = None
    current_task_id: str | None = None
    current_step: str | None = None
