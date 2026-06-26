from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class BucketMetric:
    key: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ActionMetric:
    action: str
    used: int
    success: int
    failed: int
    success_rate: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PlaybookMetric:
    playbook_id: str
    workflow_name: str
    status: str
    attempted_count: int
    success_count: int
    failure_count: int
    success_rate: float
    confidence_score: float
    last_used_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryAnalyticsSummary:
    total_recovery_incidents: int = 0
    currently_paused_recovery_tasks: int = 0
    auto_playbook_attempts: int = 0
    auto_playbook_success_rate: float = 0.0
    human_recovery_success_rate: float = 0.0
    candidate_playbooks_count: int = 0
    trusted_playbooks_count: int = 0
    playbooks_promoted_to_trusted: int = 0
    avg_pause_to_first_action_seconds: float = 0.0
    avg_pause_to_resumed_seconds: float = 0.0
    repeated_incidents_same_workflow_signature: int = 0
    incidents_by_workflow: list[BucketMetric] = field(default_factory=list)
    incidents_by_machine_uuid: list[BucketMetric] = field(default_factory=list)
    incidents_by_day: list[BucketMetric] = field(default_factory=list)
    top_problem_signatures: list[BucketMetric] = field(default_factory=list)
    top_last_error_patterns: list[BucketMetric] = field(default_factory=list)
    most_used_manual_actions: list[ActionMetric] = field(default_factory=list)
    most_successful_manual_actions: list[ActionMetric] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            **{k: v for k, v in asdict(self).items() if k not in {
                "incidents_by_workflow",
                "incidents_by_machine_uuid",
                "incidents_by_day",
                "top_problem_signatures",
                "top_last_error_patterns",
                "most_used_manual_actions",
                "most_successful_manual_actions",
            }},
            "incidents_by_workflow": [b.to_dict() for b in self.incidents_by_workflow],
            "incidents_by_machine_uuid": [b.to_dict() for b in self.incidents_by_machine_uuid],
            "incidents_by_day": [b.to_dict() for b in self.incidents_by_day],
            "top_problem_signatures": [b.to_dict() for b in self.top_problem_signatures],
            "top_last_error_patterns": [b.to_dict() for b in self.top_last_error_patterns],
            "most_used_manual_actions": [a.to_dict() for a in self.most_used_manual_actions],
            "most_successful_manual_actions": [a.to_dict() for a in self.most_successful_manual_actions],
        }
