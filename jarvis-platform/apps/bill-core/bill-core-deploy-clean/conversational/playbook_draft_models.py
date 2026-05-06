from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field


ALLOWED_PLAYBOOK_DRAFT_STATUSES = {"draft", "needs_review", "approved", "rejected"}


class PlaybookDraftStep(BaseModel):
    draft_step_id: str
    order: int
    instruction: str
    source_step_id: Optional[str] = None
    expected_result: Optional[str] = None


class PlaybookDraftDecision(BaseModel):
    draft_decision_id: str
    question: str
    condition: str
    if_true: Optional[str] = None
    if_false: Optional[str] = None
    source_decision_id: Optional[str] = None


class PlaybookDraftRule(BaseModel):
    draft_rule_id: str
    rule_text: str
    source_rule_id: Optional[str] = None
    confidence: float = 0.7


class PlaybookDraftEdgeCase(BaseModel):
    draft_edge_case_id: str
    situation: str
    expected_response: str
    source_edge_case_id: Optional[str] = None
    confidence: float = 0.7


class PlaybookDraft(BaseModel):
    draft_id: str
    tenant_id: str
    workflow_id: str
    task_name: str
    summary: str = ""
    status: str = "draft"
    steps: list[PlaybookDraftStep] = Field(default_factory=list)
    decisions: list[PlaybookDraftDecision] = Field(default_factory=list)
    rules: list[PlaybookDraftRule] = Field(default_factory=list)
    edge_cases: list[PlaybookDraftEdgeCase] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))