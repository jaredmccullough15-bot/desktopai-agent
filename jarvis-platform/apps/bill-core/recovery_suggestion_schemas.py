from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class RecoverySuggestionWarning:
    code: str
    message: str
    severity: str = "warning"  # info | warning | high

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoverySuggestionBasis:
    matched_playbook_id: str | None = None
    matched_problem_signature: str | None = None
    modal_detected: bool = False
    tab_count: int = 0
    last_error_contains: list[str] = field(default_factory=list)
    recent_action_failures: list[str] = field(default_factory=list)
    workflow_match: bool = True
    auto_playbook_failed: bool = False
    current_page_type: str | None = None
    url_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoverySuggestion:
    suggestion_id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    workflow_name: str = "unknown"
    recommended_action_sequence: list[str] = field(default_factory=list)
    primary_action: str = ""
    confidence: float = 0.5
    reasoning_summary: str = ""
    based_on: RecoverySuggestionBasis = field(default_factory=RecoverySuggestionBasis)
    warnings: list[RecoverySuggestionWarning] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    source: str = "rule_based"  # rule_based | playbook_based | ai_assisted

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_id": self.suggestion_id,
            "task_id": self.task_id,
            "workflow_name": self.workflow_name,
            "recommended_action_sequence": list(self.recommended_action_sequence),
            "primary_action": self.primary_action,
            "confidence": round(float(self.confidence), 3),
            "reasoning_summary": self.reasoning_summary,
            "based_on": self.based_on.to_dict() if hasattr(self.based_on, "to_dict") else dict(self.based_on or {}),
            "warnings": [w.to_dict() if hasattr(w, "to_dict") else w for w in self.warnings],
            "generated_at": self.generated_at,
            "source": self.source,
        }
