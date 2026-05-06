from uuid import uuid4

from conversational.playbook_draft_store import PlaybookDraftStore, playbook_draft_store
from conversational.playbook_review_models import PlaybookReview, PlaybookReviewFinding


class PlaybookReviewService:
    def __init__(self, draft_store: PlaybookDraftStore) -> None:
        self._draft_store = draft_store

    def review_draft(self, tenant_id: str, workflow_id: str, draft_id: str | None = None) -> dict:
        draft = (
            self._draft_store.get(tenant_id=tenant_id, workflow_id=workflow_id, draft_id=draft_id)
            if draft_id
            else self._draft_store.latest(tenant_id=tenant_id, workflow_id=workflow_id)
        )

        if draft is None:
            return {
                "ok": False,
                "error": "No playbook draft found for review.",
            }

        findings: list[PlaybookReviewFinding] = []

        if not draft.steps:
            findings.append(
                PlaybookReviewFinding(
                    finding_id=str(uuid4()),
                    category="missing_steps",
                    severity="blocker",
                    message="This playbook has no steps.",
                    recommendation="Teach Bill the first human action for this task.",
                )
            )

        if not draft.decisions:
            findings.append(
                PlaybookReviewFinding(
                    finding_id=str(uuid4()),
                    category="missing_decision",
                    severity="warning",
                    message="No decision points are captured.",
                    recommendation="Add at least one point where the human chooses what to do next.",
                )
            )

        if not draft.edge_cases:
            findings.append(
                PlaybookReviewFinding(
                    finding_id=str(uuid4()),
                    category="missing_edge_case",
                    severity="warning",
                    message="No edge cases are captured.",
                    recommendation="Add the most common failure or exception Bill should handle.",
                )
            )

        for step in draft.steps:
            if len((step.instruction or "").strip().split()) < 5:
                findings.append(
                    PlaybookReviewFinding(
                        finding_id=str(uuid4()),
                        category="vague_step",
                        severity="warning",
                        message=f"This step may be too vague: {step.instruction}",
                        recommendation="Rewrite this step with the exact action and expected result.",
                        source_type="step",
                        source_id=step.draft_step_id,
                    )
                )

        if draft.confidence < 0.7:
            findings.append(
                PlaybookReviewFinding(
                    finding_id=str(uuid4()),
                    category="low_confidence",
                    severity="warning",
                    message="Draft confidence is low.",
                    recommendation="Add more steps, decisions, rules, or edge cases before approval.",
                )
            )

        if draft.steps and draft.decisions and draft.edge_cases:
            findings.append(
                PlaybookReviewFinding(
                    finding_id=str(uuid4()),
                    category="readiness",
                    severity="info",
                    message="This draft has the minimum structure needed for human review.",
                    recommendation="Review the steps and approve only if they match the real task.",
                )
            )

        if draft.status == "approved":
            findings.append(
                PlaybookReviewFinding(
                    finding_id=str(uuid4()),
                    category="safety",
                    severity="info",
                    message="This draft is already approved.",
                    recommendation="Do not edit this draft directly; create a new draft if the task changed.",
                )
            )

        readiness_score = 0.0
        if draft.steps:
            readiness_score += 0.35
        if draft.decisions:
            readiness_score += 0.25
        if draft.edge_cases:
            readiness_score += 0.20
        if draft.rules:
            readiness_score += 0.10
        if draft.confidence >= 0.7:
            readiness_score += 0.10

        blockers = len([f for f in findings if f.severity == "blocker"])
        warnings = len([f for f in findings if f.severity == "warning"])
        readiness_score -= (0.10 * blockers)
        readiness_score -= (0.05 * warnings)
        readiness_score = max(0.0, min(1.0, readiness_score))

        if blockers > 0:
            overall_status = "not_ready"
        elif readiness_score >= 0.8:
            overall_status = "ready_for_human_approval"
        else:
            overall_status = "needs_review"

        review = PlaybookReview(
            review_id=str(uuid4()),
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            draft_id=draft.draft_id,
            overall_status=overall_status,
            findings=findings,
            readiness_score=readiness_score,
        )
        return {
            "ok": True,
            "review": review.model_dump(mode="json"),
        }


playbook_review_service = PlaybookReviewService(draft_store=playbook_draft_store)