from typing import Literal

from pydantic import BaseModel, Field


class ConversationRequest(BaseModel):
    tenant_id: str
    session_id: str
    message: str


class ConversationResponse(BaseModel):
    tenant_id: str
    session_id: str
    message: str
    reply: str
    action: Literal["route_only", "task_queued"] = "route_only"
    task_id: str | None = None
    routed_intent: str
    routed_action: str
    workflow_id: str | None = None
    confidence: float
    should_execute: bool
    should_clarify: bool
    should_escalate: bool
    entities: list[str] = Field(default_factory=list)
