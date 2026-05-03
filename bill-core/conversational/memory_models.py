from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkingMemoryTurn(BaseModel):
    tenant_id: str
    session_id: str
    role: Literal["user", "assistant"]
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EpisodicMemory(BaseModel):
    tenant_id: str
    session_id: str
    episode_id: str
    summary: str
    transcript: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SemanticFact(BaseModel):
    tenant_id: str
    session_id: str
    fact_key: str
    fact_value: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AssembledContext(BaseModel):
    tenant_id: str
    session_id: str
    user_message: str
    entities: list[str] = Field(default_factory=list)
    working_memory: list[WorkingMemoryTurn] = Field(default_factory=list)
    episodes: list[EpisodicMemory] = Field(default_factory=list)
    facts: list[SemanticFact] = Field(default_factory=list)
    recent_executions: list[dict[str, Any]] = Field(default_factory=list)
    workflow_success_signal: float = 0.5
