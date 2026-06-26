from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TeachingChatRequest(BaseModel):
    tenant_id: str = "default"
    workflow_id: str
    task_name: str = "Untitled Task"
    session_id: str
    message: str


class TeachingConversationState(BaseModel):
    tenant_id: str
    workflow_id: str
    session_id: str
    last_question_id: Optional[str] = None
    turn_count: int = 0
    unresolved_questions: int = 0
    teaching_mode: str = "interactive"
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TeachingChatResponse(BaseModel):
    reply: str
    task: dict[str, Any]
    next_question: Optional[dict[str, Any]] = None
    conversation_state: TeachingConversationState