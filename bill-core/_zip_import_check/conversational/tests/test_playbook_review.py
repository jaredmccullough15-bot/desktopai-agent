from uuid import uuid4

from conversational.playbook_draft_models import PlaybookDraft
from conversational.playbook_draft_store import playbook_draft_store
from conversational.playbook_generation_service import playbook_generation_service
from conversational.playbook_review_service import playbook_review_service
from conversational.task_understanding_store import task_understanding_store


def _reset_stores() -> None:
    task_understanding_store._records.clear()  # type: ignore[attr-defined]
    playbook_draft_store._drafts.clear()  # type: ignore[attr-defined]


def _make_draft_with_task(
    tenant_id: str = "tenant-1",
    workflow_id: str = "smart_sherpa_sync",
    step_description: str = "First log into Health Sherpa",
) -> dict:
    task_understanding_store.add_step(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        description=step_description,
    )
    return playbook_generation_service.generate_draft(tenant_id=tenant_id, workflow_id=workflow_id)


def test_review_with_no_draft_returns_ok_false() -> None:
    _reset_stores()

    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert result["ok"] is False
    assert result["error"] == "No playbook draft found for review."


def test_draft_with_no_steps_produces_blocker() -> None:
    _reset_stores()
    draft = PlaybookDraft(
        draft_id=str(uuid4()),
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        task_name="Smart Sherpa Sync",
        steps=[],
    )
    playbook_draft_store.save(draft)

    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=draft.draft_id,
    )

    blockers = [f for f in result["review"]["findings"] if f["severity"] == "blocker"]
    assert result["ok"] is True
    assert len(blockers) >= 1
    assert blockers[0]["category"] == "missing_steps"


def test_steps_without_decisions_produces_warning() -> None:
    _reset_stores()
    generated = _make_draft_with_task()

    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    categories = [f["category"] for f in result["review"]["findings"]]
    assert "missing_decision" in categories


def test_steps_without_edge_cases_produces_warning() -> None:
    _reset_stores()
    generated = _make_draft_with_task()

    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    categories = [f["category"] for f in result["review"]["findings"]]
    assert "missing_edge_case" in categories


def test_vague_short_step_produces_vague_step_warning() -> None:
    _reset_stores()
    generated = _make_draft_with_task(step_description="Click next")

    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    categories = [f["category"] for f in result["review"]["findings"]]
    assert "vague_step" in categories


def test_complete_draft_gets_readiness_info_finding() -> None:
    _reset_stores()
    task_understanding_store.add_step(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        description="First log into Health Sherpa and open the client list",
    )
    task_understanding_store.add_decision(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        question="If client exists",
        condition="if client exists",
        if_true="open profile",
        if_false="create client",
    )
    task_understanding_store.add_edge_case(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        situation="Portal timeout",
        expected_response="Refresh and retry once",
    )
    task_understanding_store.add_rule(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        rule_text="Always verify DOB before submitting",
    )
    task = task_understanding_store.get("tenant-1", "smart_sherpa_sync")
    assert task is not None
    task.confidence = 0.8

    generated = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )
    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    categories = [f["category"] for f in result["review"]["findings"]]
    assert "readiness" in categories


def test_readiness_score_stays_between_zero_and_one() -> None:
    _reset_stores()
    generated = _make_draft_with_task()
    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    score = result["review"]["readiness_score"]
    assert 0.0 <= score <= 1.0


def test_approved_draft_gets_safety_info_finding() -> None:
    _reset_stores()
    generated = _make_draft_with_task(step_description="First log into Health Sherpa and review clients")
    approved = playbook_generation_service.approve_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )
    assert approved["ok"] is True

    result = playbook_review_service.review_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    categories = [f["category"] for f in result["review"]["findings"]]
    assert "safety" in categories


def test_not_ready_draft_cannot_be_approved_when_blocking_enabled() -> None:
    _reset_stores()
    draft = PlaybookDraft(
        draft_id=str(uuid4()),
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        task_name="Smart Sherpa Sync",
        steps=[],
    )
    playbook_draft_store.save(draft)

    result = playbook_generation_service.approve_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=draft.draft_id,
    )

    assert result["ok"] is False
    assert result["error"] == "Playbook draft is not ready for approval."