"""Tests for BillChatService (Phase 9: Conversational Command Center Adapter).

All tests use injected stubs — no live state, no DB, no HTTP calls.
"""
from __future__ import annotations

from typing import Any

import pytest

from conversational.bill_chat_service import (
    BillChatRequest,
    BillChatResponse,
    BillChatService,
    _detect_intent,
    _extract_workflow_name,
    _parse_rename_command,
)

# ---------------------------------------------------------------------------
# Stubs / helpers
# ---------------------------------------------------------------------------


class StubTaskService:
    """Records task payloads and returns a fake TaskCreateResponse."""

    def __init__(self, task_id: str = "task-abc-123") -> None:
        self._task_id = task_id
        self.calls: list[dict[str, Any]] = []

    def create(self, payload: dict[str, Any]) -> Any:
        self.calls.append(dict(payload))

        class _Rec:
            id = self._task_id

        return _Rec()


class StubWorkerRegistry:
    """In-memory worker registry for tests."""

    def __init__(self, workers: dict[str, dict] | None = None) -> None:
        self._workers: dict[str, dict] = workers or {}
        self.rename_calls: list[tuple[str, str]] = []

    def get_workers(self) -> dict[str, dict]:
        return dict(self._workers)

    def rename_worker(self, machine_uuid: str, new_name: str) -> dict[str, Any]:
        if machine_uuid not in self._workers:
            raise ValueError(f"Worker {machine_uuid!r} not found")
        old_name = self._workers[machine_uuid].get("machine_name", "")
        self._workers[machine_uuid]["machine_name"] = new_name
        self.rename_calls.append((machine_uuid, new_name))
        return {"machine_uuid": machine_uuid, "old_name": old_name, "machine_name": new_name}


def _make_service(
    task_stub: StubTaskService | None = None,
    worker_registry: StubWorkerRegistry | None = None,
) -> tuple[BillChatService, StubTaskService, StubWorkerRegistry]:
    ts = task_stub or StubTaskService()
    wr = worker_registry or StubWorkerRegistry()
    service = BillChatService(
        create_task_fn=ts.create,
        get_workers_fn=wr.get_workers,
        rename_worker_fn=wr.rename_worker,
    )
    return service, ts, wr


def _req(message: str, **kwargs: Any) -> BillChatRequest:
    return BillChatRequest(
        tenant_id="internal",
        user_id="user-1",
        session_id="session-1",
        message=message,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1. "start a new workflow" without a name → asks for name
# ---------------------------------------------------------------------------


def test_start_new_workflow_no_name_asks_for_name() -> None:
    service, ts, _ = _make_service()
    response = service.handle_message(_req("start a new workflow"))

    assert response.intent == "start_new_workflow"
    assert response.next_required_input == "workflow_name"
    assert "call" in response.reply.lower() or "name" in response.reply.lower()
    assert ts.calls == [], "No task should be queued when name is missing"


# ---------------------------------------------------------------------------
# 2. Workflow name provided → queues a teach_session task
# ---------------------------------------------------------------------------


def test_start_new_workflow_with_name_queues_teach_session() -> None:
    service, ts, _ = _make_service()
    response = service.handle_message(_req("start a new workflow called PatientIntake"))

    assert response.intent == "start_new_workflow"
    assert response.action == "task_queued"
    assert response.task_id == "task-abc-123"
    assert len(ts.calls) == 1
    assert ts.calls[0]["task_type"] == "teach_session"
    assert "PatientIntake" in ts.calls[0]["workflow_name"]
    assert "PatientIntake" in response.reply


# ---------------------------------------------------------------------------
# 3. "worker status" → returns worker list
# ---------------------------------------------------------------------------


def test_worker_status_returns_worker_info() -> None:
    wr = StubWorkerRegistry({
        "uuid-001": {"machine_name": "BillWorker-PC", "status": "idle"},
        "uuid-002": {"machine_name": "BillWorker-Laptop", "status": "busy"},
    })
    service, _, _ = _make_service(worker_registry=wr)
    response = service.handle_message(_req("worker status"))

    assert response.intent == "worker_status"
    assert response.metadata["worker_count"] == 2
    assert "BillWorker-PC" in response.reply
    assert "BillWorker-Laptop" in response.reply
    names = [w["name"] for w in response.metadata["workers"]]
    assert "BillWorker-PC" in names
    assert "BillWorker-Laptop" in names


def test_worker_status_no_workers() -> None:
    service, _, _ = _make_service(worker_registry=StubWorkerRegistry({}))
    response = service.handle_message(_req("show workers"))

    assert response.intent == "worker_status"
    assert response.metadata["worker_count"] == 0
    assert "no workers" in response.reply.lower()


# ---------------------------------------------------------------------------
# 4. "run smart sherpa" → queues batch task with strict flags
# ---------------------------------------------------------------------------


def test_run_smart_sherpa_queues_batch_task() -> None:
    service, ts, _ = _make_service()
    response = service.handle_message(_req("run smart sherpa"))

    assert response.intent == "run_smart_sherpa"
    assert response.action == "task_queued"
    assert response.workflow_id == "smart_sherpa_sync"
    assert len(ts.calls) == 1
    payload = ts.calls[0]
    assert payload["task_type"] == "smart_sherpa_sync"
    assert payload["run_mode"] == "batch"
    assert payload["attach_to_existing"] is True
    assert payload["require_existing_page"] is True
    assert payload["allow_launch_fallback"] is False
    assert payload["browser_profile_policy"] == "attach_existing_debug"
    assert "smart sherpa" in response.reply.lower()


# ---------------------------------------------------------------------------
# 5. "rename worker" → updates worker name correctly
# ---------------------------------------------------------------------------


def test_rename_worker_by_name_succeeds() -> None:
    wr = StubWorkerRegistry({"uuid-abc": {"machine_name": "OldWorker", "status": "idle"}})
    service, _, registry = _make_service(worker_registry=wr)
    response = service.handle_message(_req("rename worker OldWorker to NewWorker"))

    assert response.intent == "rename_worker"
    assert response.action == "worker_renamed"
    assert "NewWorker" in response.reply
    assert registry.rename_calls == [("uuid-abc", "NewWorker")]
    # Confirm the in-memory registry was mutated
    assert wr._workers["uuid-abc"]["machine_name"] == "NewWorker"


def test_rename_worker_by_uuid_succeeds() -> None:
    uuid = "a1b2c3d4-0000-0000-0000-000000000001"
    wr = StubWorkerRegistry({uuid: {"machine_name": "WorkerAlpha", "status": "idle"}})
    service, _, registry = _make_service(worker_registry=wr)
    response = service.handle_message(_req(f"rename worker {uuid} to WorkerBeta"))

    assert response.action == "worker_renamed"
    assert registry.rename_calls == [(uuid, "WorkerBeta")]


def test_rename_worker_no_target_asks_for_clarification() -> None:
    service, _, _ = _make_service()
    response = service.handle_message(_req("rename worker"))

    assert response.intent == "rename_worker"
    assert response.next_required_input is not None
    assert response.action is None


def test_rename_worker_missing_new_name_asks_for_name() -> None:
    wr = StubWorkerRegistry({"uuid-x": {"machine_name": "SomeWorker", "status": "idle"}})
    service, _, _ = _make_service(worker_registry=wr)
    # "SomeWorker" identified but no "to <name>" present
    response = service.handle_message(_req("rename worker SomeWorker"))

    assert response.intent == "rename_worker"
    assert response.next_required_input == "new_name"
    assert response.metadata.get("target_uuid") == "uuid-x"


# ---------------------------------------------------------------------------
# 6. Worker rename persists across calls
# ---------------------------------------------------------------------------


def test_rename_worker_persists_in_registry() -> None:
    wr = StubWorkerRegistry({"uuid-persist": {"machine_name": "Alpha", "status": "idle"}})
    service, _, registry = _make_service(worker_registry=wr)

    # First rename: Alpha → Beta
    r1 = service.handle_message(_req("rename worker Alpha to Beta"))
    assert r1.action == "worker_renamed"
    assert wr._workers["uuid-persist"]["machine_name"] == "Beta"

    # Second rename: Beta → Gamma  — must find by the UPDATED name, not original
    r2 = service.handle_message(_req("rename worker Beta to Gamma"))
    assert r2.action == "worker_renamed"
    assert wr._workers["uuid-persist"]["machine_name"] == "Gamma"
    # Two rename calls total
    assert len(registry.rename_calls) == 2


# ---------------------------------------------------------------------------
# 7. No existing functionality is broken
# ---------------------------------------------------------------------------


def test_fallback_intent_returns_helpful_reply() -> None:
    service, ts, _ = _make_service()
    response = service.handle_message(_req("Hello Bill"))

    assert response.intent == "conversation"
    assert ts.calls == []
    assert response.reply  # non-empty


def test_start_teach_session_queues_task() -> None:
    service, ts, _ = _make_service()
    response = service.handle_message(_req("teach bill this workflow"))

    assert response.intent == "start_teach_session"
    assert response.action == "task_queued"
    assert len(ts.calls) == 1
    assert ts.calls[0]["task_type"] == "teach_session"


def test_intent_detection_smoke() -> None:
    assert _detect_intent("start a new workflow") == "start_new_workflow"
    assert _detect_intent("create workflow") == "start_new_workflow"
    assert _detect_intent("new workflow") == "start_new_workflow"
    assert _detect_intent("teach bill") == "start_teach_session"
    assert _detect_intent("teach this") == "start_teach_session"
    assert _detect_intent("start teaching") == "start_teach_session"
    assert _detect_intent("worker status") == "worker_status"
    assert _detect_intent("show workers") == "worker_status"
    assert _detect_intent("who is online") == "worker_status"
    assert _detect_intent("run smart sherpa") == "run_smart_sherpa"
    assert _detect_intent("start sherpa sync") == "run_smart_sherpa"
    assert _detect_intent("rename worker") == "rename_worker"
    assert _detect_intent("change worker name") == "rename_worker"
    assert _detect_intent("something random") == "conversation"


def test_extract_workflow_name() -> None:
    assert _extract_workflow_name("new workflow called PatientIntake") == "PatientIntake"
    assert _extract_workflow_name("create workflow named BillingFlow") == "BillingFlow"
    assert _extract_workflow_name("start a new workflow") is None


def test_parse_rename_command_by_name() -> None:
    workers = {"uuid-1": {"machine_name": "OldName", "status": "idle"}}
    uuid, name = _parse_rename_command("rename worker OldName to NewName", workers)
    assert uuid == "uuid-1"
    assert name == "NewName"


def test_parse_rename_command_by_uuid() -> None:
    uid = "a1b2c3d4-0000-0000-0000-000000000001"
    workers = {uid: {"machine_name": "SomeWorker", "status": "idle"}}
    uuid, name = _parse_rename_command(f"rename worker {uid} to FancyName", workers)
    assert uuid == uid
    assert name == "FancyName"


def test_task_queued_without_target_machine_omits_field() -> None:
    """target_machine_uuid should NOT be injected into task payload when absent."""
    service, ts, _ = _make_service()
    service.handle_message(_req("run smart sherpa"))
    assert "target_machine_uuid" not in ts.calls[0]


def test_task_queued_with_target_machine_passes_field() -> None:
    """target_machine_uuid is forwarded when set on teach_session requests."""
    service, ts, _ = _make_service()
    service.handle_message(_req("start a new workflow called X", target_machine_uuid="uuid-worker-1"))
    assert ts.calls[0].get("target_machine_uuid") == "uuid-worker-1"
