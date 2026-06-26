from conversational.playbook_draft_store import playbook_draft_store
from conversational.playbook_generation_service import playbook_generation_service
from conversational.task_understanding_store import task_understanding_store


def _reset_stores() -> None:
    task_understanding_store._records.clear()  # type: ignore[attr-defined]
    playbook_draft_store._drafts.clear()  # type: ignore[attr-defined]


def test_generate_draft_without_task_understanding_returns_error() -> None:
    _reset_stores()

    result = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert result["ok"] is False
    assert result["error"] == "No task understanding found for this workflow."


def test_generate_draft_without_steps_returns_error() -> None:
    _reset_stores()
    task_understanding_store.create_or_get(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        task_name="Smart Sherpa Sync",
    )

    result = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert result["ok"] is False
    assert result["error"] == "Cannot generate playbook draft without at least one step."


def test_generate_draft_with_steps_creates_draft() -> None:
    _reset_stores()
    task_understanding_store.add_step(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        description="First log into Health Sherpa.",
    )

    result = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert result["ok"] is True
    assert result["draft"]["workflow_id"] == "smart_sherpa_sync"
    assert len(result["draft"]["steps"]) == 1


def test_generate_draft_includes_warnings_without_decisions_or_edge_cases() -> None:
    _reset_stores()
    task_understanding_store.add_step(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        description="First log into Health Sherpa.",
    )

    result = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert result["ok"] is True
    warnings = result["draft"]["warnings"]
    assert "No decision points captured yet." in warnings
    assert "No edge cases captured yet." in warnings


def test_approve_draft_changes_status_to_approved() -> None:
    _reset_stores()
    task_understanding_store.add_step(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        description="First log into Health Sherpa.",
    )
    generated = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    result = playbook_generation_service.approve_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    assert result["ok"] is True
    assert result["draft"]["status"] == "approved"


def test_reject_draft_changes_status_to_rejected() -> None:
    _reset_stores()
    task_understanding_store.add_step(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        description="First log into Health Sherpa.",
    )
    generated = playbook_generation_service.generate_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    result = playbook_generation_service.reject_draft(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        draft_id=generated["draft"]["draft_id"],
    )

    assert result["ok"] is True
    assert result["draft"]["status"] == "rejected"


def test_playbook_draft_tenant_isolation_works() -> None:
    _reset_stores()
    task_understanding_store.add_step(
        tenant_id="tenant-a",
        workflow_id="smart_sherpa_sync",
        description="First do A.",
    )
    task_understanding_store.add_step(
        tenant_id="tenant-b",
        workflow_id="smart_sherpa_sync",
        description="First do B.",
    )

    playbook_generation_service.generate_draft(tenant_id="tenant-a", workflow_id="smart_sherpa_sync")
    playbook_generation_service.generate_draft(tenant_id="tenant-b", workflow_id="smart_sherpa_sync")

    tenant_a = playbook_draft_store.list_by_tenant("tenant-a")
    tenant_b = playbook_draft_store.list_by_tenant("tenant-b")

    assert len(tenant_a) == 1
    assert len(tenant_b) == 1
    assert tenant_a[0].tenant_id == "tenant-a"
    assert tenant_b[0].tenant_id == "tenant-b"