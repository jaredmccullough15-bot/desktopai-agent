from uuid import uuid4

from conversational.playbook_draft_models import (
    PlaybookDraft,
    PlaybookDraftDecision,
    PlaybookDraftEdgeCase,
    PlaybookDraftRule,
    PlaybookDraftStep,
)
from conversational.playbook_draft_store import PlaybookDraftStore, playbook_draft_store
from conversational.task_understanding_store import TaskUnderstandingStore, task_understanding_store


class PlaybookGenerationService:
    def __init__(self, task_store: TaskUnderstandingStore, draft_store: PlaybookDraftStore) -> None:
        self._task_store = task_store
        self._draft_store = draft_store

    def generate_draft(self, tenant_id: str, workflow_id: str) -> dict:
        task = self._task_store.get(tenant_id=tenant_id, workflow_id=workflow_id)
        if task is None:
            return {
                "ok": False,
                "error": "No task understanding found for this workflow.",
            }

        if not task.steps:
            return {
                "ok": False,
                "error": "Cannot generate playbook draft without at least one step.",
            }

        steps = [
            PlaybookDraftStep(
                draft_step_id=str(uuid4()),
                order=step.order,
                instruction=step.description,
                source_step_id=step.step_id,
                expected_result=step.expected_result,
            )
            for step in task.steps
        ]
        decisions = [
            PlaybookDraftDecision(
                draft_decision_id=str(uuid4()),
                question=decision.question,
                condition=decision.condition,
                if_true=decision.if_true,
                if_false=decision.if_false,
                source_decision_id=decision.decision_id,
            )
            for decision in task.decisions
        ]
        rules = [
            PlaybookDraftRule(
                draft_rule_id=str(uuid4()),
                rule_text=rule.rule_text,
                source_rule_id=rule.rule_id,
                confidence=rule.confidence,
            )
            for rule in task.rules
        ]
        edge_cases = [
            PlaybookDraftEdgeCase(
                draft_edge_case_id=str(uuid4()),
                situation=edge_case.situation,
                expected_response=edge_case.expected_response,
                source_edge_case_id=edge_case.edge_case_id,
                confidence=edge_case.confidence,
            )
            for edge_case in task.edge_cases
        ]

        warnings: list[str] = []
        if not decisions:
            warnings.append("No decision points captured yet.")
        if not edge_cases:
            warnings.append("No edge cases captured yet.")
        if task.confidence < 0.7:
            warnings.append("Task understanding confidence is still low.")

        confidence = 0.5
        if steps:
            confidence += 0.2
        if decisions:
            confidence += 0.1
        if rules:
            confidence += 0.1
        if edge_cases:
            confidence += 0.1
        confidence = min(1.0, confidence)

        draft = PlaybookDraft(
            draft_id=str(uuid4()),
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            task_name=task.task_name,
            summary=task.summary,
            status="needs_review" if warnings else "draft",
            steps=steps,
            decisions=decisions,
            rules=rules,
            edge_cases=edge_cases,
            warnings=warnings,
            confidence=confidence,
        )
        saved = self._draft_store.save(draft)
        return {
            "ok": True,
            "draft": saved.model_dump(mode="json"),
        }

    def approve_draft(self, tenant_id: str, workflow_id: str, draft_id: str) -> dict:
        from conversational.playbook_review_service import playbook_review_service

        review_result = playbook_review_service.review_draft(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            draft_id=draft_id,
        )
        if review_result.get("ok") is False:
            return {
                "ok": False,
                "error": str(review_result.get("error") or "No playbook draft found for review."),
            }

        review_payload = review_result.get("review", {})
        if review_payload.get("overall_status") == "not_ready":
            return {
                "ok": False,
                "error": "Playbook draft is not ready for approval.",
                "review": review_payload,
            }

        try:
            draft = self._draft_store.update_status(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                draft_id=draft_id,
                status="approved",
            )
        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        return {
            "ok": True,
            "draft": draft.model_dump(mode="json"),
        }

    def reject_draft(self, tenant_id: str, workflow_id: str, draft_id: str) -> dict:
        try:
            draft = self._draft_store.update_status(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                draft_id=draft_id,
                status="rejected",
            )
        except ValueError as exc:
            return {
                "ok": False,
                "error": str(exc),
            }

        return {
            "ok": True,
            "draft": draft.model_dump(mode="json"),
        }


playbook_generation_service = PlaybookGenerationService(
    task_store=task_understanding_store,
    draft_store=playbook_draft_store,
)