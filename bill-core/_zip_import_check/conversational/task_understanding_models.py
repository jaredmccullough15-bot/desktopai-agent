from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskStep(BaseModel):
    step_id: str
    order: int
    description: str
    screen_hint: Optional[str] = None
    expected_result: Optional[str] = None


class TaskDecision(BaseModel):
    decision_id: str
    question: str
    condition: str
    if_true: Optional[str] = None
    if_false: Optional[str] = None


class TaskRule(BaseModel):
    rule_id: str
    rule_text: str
    confidence: float = 0.7
    source: str = "teaching"


class TaskEdgeCase(BaseModel):
    edge_case_id: str
    situation: str
    expected_response: str
    confidence: float = 0.7


class TaskOpenQuestion(BaseModel):
    question_id: str
    question: str
    reason: str
    priority: str = "medium"
    answered: bool = False
    answer: Optional[str] = None


class TaskUnderstanding(BaseModel):
    task_id: str
    tenant_id: str
    workflow_id: str
    task_name: str
    summary: str = ""
    steps: list[TaskStep] = Field(default_factory=list)
    decisions: list[TaskDecision] = Field(default_factory=list)
    rules: list[TaskRule] = Field(default_factory=list)
    edge_cases: list[TaskEdgeCase] = Field(default_factory=list)
    open_questions: list[TaskOpenQuestion] = Field(default_factory=list)
    confidence: float = 0.5
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))