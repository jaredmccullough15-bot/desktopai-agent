from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


ALLOWED_EXECUTION_STATUSES = {"queued", "running", "completed", "failed", "paused"}


class ExecutionRecord:
	def __init__(
		self,
		tenant_id: str,
		user_id: str,
		workflow_id: str,
		task_id: str,
		confidence: float,
		context_snapshot: dict[str, Any],
		intent: str,
		status: str = "queued",
	):
		self.execution_id = str(uuid4())
		self.tenant_id = tenant_id
		self.user_id = user_id
		self.workflow_id = workflow_id
		self.task_id = task_id
		self.confidence = confidence
		self.intent = intent
		self.context_snapshot = context_snapshot
		self.status = status if status in ALLOWED_EXECUTION_STATUSES else "queued"
		self.created_at = datetime.now(timezone.utc)

	def to_dict(self) -> dict[str, Any]:
		return {
			"execution_id": self.execution_id,
			"tenant_id": self.tenant_id,
			"user_id": self.user_id,
			"workflow_id": self.workflow_id,
			"task_id": self.task_id,
			"confidence": self.confidence,
			"intent": self.intent,
			"context_snapshot": self.context_snapshot,
			"status": self.status,
			"created_at": self.created_at.isoformat(),
		}


class ExecutionTracker:
	def __init__(self):
		self.records: list[ExecutionRecord] = []

	def log_execution(
		self,
		tenant_id: str,
		user_id: str,
		workflow_id: str,
		task_id: str,
		confidence: float,
		context_snapshot: dict[str, Any],
		intent: str,
		status: str = "queued",
	):
		record = ExecutionRecord(
			tenant_id=tenant_id,
			user_id=user_id,
			workflow_id=workflow_id,
			task_id=task_id,
			confidence=confidence,
			context_snapshot=context_snapshot,
			intent=intent,
			status=status,
		)

		self.records.append(record)

	def get_recent(self, tenant_id: str, limit: int = 10):
		return [
			r for r in reversed(self.records)
			if r.tenant_id == tenant_id
		][:limit]

	def get_recent_for_workflow(self, tenant_id: str, workflow_id: str, limit: int = 10):
		return [
			r for r in reversed(self.records)
			if r.tenant_id == tenant_id and r.workflow_id == workflow_id
		][:limit]

	def mark_status(self, tenant_id: str, task_id: str, status: str) -> bool:
		if status not in ALLOWED_EXECUTION_STATUSES:
			return False

		for record in reversed(self.records):
			if record.tenant_id == tenant_id and record.task_id == task_id:
				record.status = status
				return True

		return False

	def get_workflow_success_signal(self, tenant_id: str, workflow_id: str) -> float:
		recent = self.get_recent_for_workflow(tenant_id=tenant_id, workflow_id=workflow_id, limit=10)
		if not recent:
			return 0.5

		signal = 0.5
		for record in recent:
			if record.status == "completed":
				signal += 0.15
			elif record.status == "failed":
				signal -= 0.2
			elif record.status == "paused":
				signal -= 0.1

		return max(0.0, min(1.0, signal))


execution_tracker = ExecutionTracker()
