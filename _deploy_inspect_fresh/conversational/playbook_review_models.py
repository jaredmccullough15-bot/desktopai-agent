from datetime import UTC, datetime
from typing import Optional

from pydantic import BaseModel, Field


ALLOWED_REVIEW_SEVERITIES = {"info", "warning", "blocker"}
ALLOWED_REVIEW_CATEGORIES = {
    "missing_steps",
    "vague_step",
    "missing_decision",
    "missing_edge_case",
    "low_confidence",
    "readiness",
    "safety",
}
ALLOWED_REVIEW_OVERALL_STATUSES = {"not_ready", "needs_review", "ready_for_human_approval"}


class PlaybookReviewFinding(BaseModel):
    finding_id: str
    severity: str
    category: str
    message: str
    recommendation: str
    source_type: Optional[str] = None
    source_id: Optional[str] = None


class PlaybookReview(BaseModel):
    review_id: str
    tenant_id: str
    workflow_id: str
    draft_id: str
    overall_status: str
    findings: list[PlaybookReviewFinding] = Field(default_factory=list)
    readiness_score: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))