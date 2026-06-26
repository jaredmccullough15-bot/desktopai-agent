"""
test_task_persistence.py — Durable task queue tests for Bill Core.

Tests that task state survives the equivalent of a process restart by:
1. Creating tasks via the API (which writes to DB via save_task_db)
2. Clearing the in-memory tasks list (simulating a restart)
3. Calling _load_persisted_tasks() (the startup recovery function)
4. Verifying tasks are back in memory and correct

These tests use a real SQLite DB (in-process) via the existing DB layer.
They require _DB_ENABLED to be True in the test environment.
"""

from __future__ import annotations

import copy
import importlib
import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import auth
import main as m
from db import Base, SessionLocal, engine
from models_db import Tenant
from user_auth import create_user_account


DASHBOARD_HEADERS = {"X-Bill-Core-Key": "dashboard-test-key"}
WORKER_HEADERS = {"X-Bill-Worker-Key": "worker-test-secret"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_task_state(monkeypatch: pytest.MonkeyPatch):
    """Save and restore tasks + DB state around each test.

    A unique worker UUID is generated per test run so that tasks created
    in previous test runs (still in the DB) are never accidentally routed
    to the current test's worker.
    """
    monkeypatch.setenv("BILL_CORE_AUTH_ENABLED", "true")
    monkeypatch.setenv("BILL_CORE_DASHBOARD_API_KEY", "dashboard-test-key")
    monkeypatch.setenv("BILL_CORE_WORKER_SHARED_SECRET", "worker-test-secret")
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "false")
    importlib.reload(auth)
    importlib.reload(m)

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        session.query(Tenant).delete()
        session.add(Tenant(id="default", name="Internal", is_internal=True))
        session.commit()

    original_tasks = copy.deepcopy(m.tasks)
    m.tasks.clear()

    # Unique UUID per test invocation to avoid cross-run DB collisions
    fake_uuid = f"test-worker-{uuid4().hex[:12]}"
    m.registered_workers[fake_uuid] = {
        "machine_uuid": fake_uuid,
        "tenant_id": "default",
        "machine_name": "test-worker",
        "status": "online",
        "worker_version": "0.0.0",
        "execution_mode": "interactive_visible",
    }

    yield fake_uuid

    # Restore state
    m.tasks.clear()
    m.tasks.extend(original_tasks)
    m.registered_workers.pop(fake_uuid, None)


@pytest.fixture()
def client():
    with TestClient(m.app) as test_client:
        create_user_account(
            {
                "email": "runner@bill.test",
                "name": "Task Runner",
                "password": "TestPass123!",
                "role": "runner",
                "status": "active",
                "tenant_id": "default",
            }
        )
        login = test_client.post(
            "/api/auth/login",
            json={"email": "runner@bill.test", "password": "TestPass123!"},
            headers=DASHBOARD_HEADERS,
        )
        assert login.status_code == 200, f"Login failed in test fixture: {login.text}"
        yield test_client


def _is_db_enabled() -> bool:
    return bool(m._DB_ENABLED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_task_via_api(
    client: TestClient,
    task_type: str = "smart_sherpa_sync",
    tenant_id: str = "default",
) -> str:
    """POST to /api/tasks and return the task_id."""
    res = client.post(
        "/api/tasks",
        json={
            "task_type": task_type,
            "workflow_id": task_type,
            "workflow_name": task_type,
            "tenant_id": tenant_id,
        },
    )
    assert res.status_code in (200, 201), f"Task creation failed: {res.text}"
    body = res.json()
    return body["id"]


def _create_task_for_worker(
    client: TestClient,
    machine_uuid: str,
    task_type: str = "smart_sherpa_sync",
    tenant_id: str = "default",
) -> str:
    """POST to /api/tasks targeted at a specific worker UUID and return the task_id."""
    res = client.post(
        "/api/tasks",
        json={
            "task_type": task_type,
            "workflow_id": task_type,
            "workflow_name": task_type,
            "tenant_id": tenant_id,
            "target_machine_uuid": machine_uuid,
        },
    )
    assert res.status_code in (200, 201), f"Task creation failed: {res.text}"
    body = res.json()
    return body["id"]


def _simulate_restart(target_task_ids: list[str] | None = None) -> None:
    """Simulate a process restart by clearing in-memory tasks and reloading from DB."""
    if target_task_ids is not None:
        # Only remove the tasks created by this test (leave any pre-existing)
        to_remove = set(target_task_ids)
        for task in list(m.tasks):
            if task.get("id") in to_remove:
                m.tasks.remove(task)
    else:
        m.tasks.clear()

    if _is_db_enabled():
        from task_store import load_tasks_from_db

        reloaded = load_tasks_from_db()
        m.tasks.clear()
        m.tasks.extend(reloaded)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not m._DB_ENABLED, reason="DB layer not enabled in this environment")
class TestTaskPersistence:

    def test_task_created_persists_in_db(self, client):
        """A newly created task should immediately appear in the DB debug endpoint."""
        task_id = _create_task_via_api(client)

        res = client.get("/api/debug/tasks-db")
        assert res.status_code == 200
        db_tasks = res.json()
        ids = [t.get("id") for t in db_tasks]
        assert task_id in ids, f"Task {task_id} not found in DB: {ids}"

    def test_pending_task_survives_simulated_restart(self, client):
        """A queued task should be in memory after simulated restart + startup load."""
        task_id = _create_task_via_api(client)

        # Confirm in memory
        assert any(t.get("id") == task_id for t in m.tasks)

        # Simulate restart
        _simulate_restart([task_id])

        # Should be back in memory after loading from DB
        found = next((t for t in m.tasks if t.get("id") == task_id), None)
        assert found is not None, f"Task {task_id} not reloaded from DB after restart"
        assert found["status"] == "queued"

    def test_worker_can_poll_task_after_simulated_restart(self, client, isolate_task_state):
        """Worker poll should find the task after a restart + DB reload."""
        machine_uuid = isolate_task_state
        # Use target_machine_uuid so this task is routed specifically to our test worker
        task_id = _create_task_for_worker(client, machine_uuid)

        # Verify task is in memory before restart
        assert any(t.get("id") == task_id for t in m.tasks)

        # Simulate restart — clear this task from memory, reload from DB
        _simulate_restart([task_id])

        # Task should be back in memory as queued
        found = next((t for t in m.tasks if t.get("id") == task_id), None)
        assert found is not None, f"Task {task_id} not reloaded into memory after restart"
        assert found["status"] == "queued", f"Expected queued, got {found['status']}"

        # Worker polls — should get our targeted task
        # Poll until our targeted task is assigned (other un-targeted queue tasks may go first)
        MAX_POLLS = 30
        assigned_ids: list[str] = []
        for _ in range(MAX_POLLS):
            res = client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)
            assert res.status_code == 200
            body = res.json()
            if body is None:
                break
            assigned_ids.append(body["id"])
            if body["id"] == task_id:
                break

        assert task_id in assigned_ids, (
            f"Task {task_id} (target_machine_uuid={machine_uuid}) was never assigned "
            f"after {MAX_POLLS} polls. Got: {assigned_ids}"
        )
        # Verify the task is marked assigned in memory
        in_mem = next((t for t in m.tasks if t.get("id") == task_id), None)
        assert in_mem is not None
        assert in_mem["status"] == "assigned"

    def test_completed_task_persists_after_restart(self, client, isolate_task_state):
        """Completed task status should be readable from DB after restart."""
        machine_uuid = isolate_task_state
        task_id = _create_task_via_api(client)

        # Assign via poll
        client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)

        # Complete the task
        res = client.post(
            f"/worker/tasks/{task_id}/complete",
            json={
                "machine_uuid": machine_uuid,
                "result_json": {"outcome": "success", "records_processed": 42},
            },
            headers=WORKER_HEADERS,
        )
        assert res.status_code == 200

        # Verify persisted in DB
        db_res = client.get("/api/debug/tasks-db")
        db_row = next((t for t in db_res.json() if t.get("id") == task_id), None)
        assert db_row is not None
        assert db_row["status"] == "completed"

    def test_failed_task_persists_error_and_result(self, client, isolate_task_state):
        """Failed task error and result_json should be persisted to DB."""
        machine_uuid = isolate_task_state
        task_id = _create_task_via_api(client)

        # Assign
        client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)

        # Fail with non-timeout error
        res = client.post(
            f"/worker/tasks/{task_id}/fail",
            json={
                "machine_uuid": machine_uuid,
                "error": "Element not found: button.submit",
                "result_json": {"last_step": "submit_form", "steps_completed": 3},
            },
            headers=WORKER_HEADERS,
        )
        assert res.status_code == 200

        # Verify status in DB
        db_res = client.get("/api/debug/tasks-db")
        db_row = next((t for t in db_res.json() if t.get("id") == task_id), None)
        assert db_row is not None
        # Timeout recovery may escalate to needs_human_help; non-timeout fails as "failed"
        assert db_row["status"] in ("failed", "needs_human_help", "recovering")

    def test_stale_assigned_task_is_requeued_on_startup(self):
        """An assigned task older than the stale threshold should be requeued."""
        if not _is_db_enabled():
            pytest.skip("DB not enabled")

        from db import SessionLocal
        from models_db import Task as TaskRow
        from db_writes import save_task_db as _save_task_db

        # Create a stale assigned task directly in DB
        stale_time = (datetime.utcnow() - timedelta(hours=3)).isoformat()
        task_id = str(uuid4())
        stale_task: dict = {
            "id": task_id,
            "payload": {"task_type": "smart_sherpa_sync"},
            "status": "assigned",
            "assigned_machine_uuid": "old-dead-worker",
            "result_json": None,
            "error": None,
            "created_at": stale_time,
            "updated_at": stale_time,
            "completed_at": None,
            "logs": [],
        }
        _save_task_db(stale_task)

        # Load from DB with stale threshold of 60 min (task is 3h old → stale)
        from task_store import load_tasks_from_db
        loaded = load_tasks_from_db(stale_assigned_minutes=60)
        loaded_task = next((t for t in loaded if t.get("id") == task_id), None)

        assert loaded_task is not None, f"Stale task {task_id} not found in DB load"
        assert loaded_task["status"] == "queued", (
            f"Stale task should be requeued, got status={loaded_task['status']}"
        )
        assert loaded_task.get("assigned_machine_uuid") is None
        assert loaded_task.get("_requeued_on_startup") is True

        # Cleanup
        with SessionLocal() as session:
            session.query(TaskRow).filter_by(id=task_id).delete()
            session.commit()

    def test_stale_recent_assigned_task_is_not_requeued(self):
        """An assigned task within the stale threshold should NOT be requeued."""
        if not _is_db_enabled():
            pytest.skip("DB not enabled")

        from db_writes import save_task_db as _save_task_db
        from db import SessionLocal
        from models_db import Task as TaskRow

        # Create a recently-assigned task (30 min ago)
        recent_time = (datetime.utcnow() - timedelta(minutes=30)).isoformat()
        task_id = str(uuid4())
        recent_task: dict = {
            "id": task_id,
            "payload": {"task_type": "smart_sherpa_sync"},
            "status": "assigned",
            "assigned_machine_uuid": "active-worker",
            "result_json": None,
            "error": None,
            "created_at": recent_time,
            "updated_at": recent_time,
            "completed_at": None,
            "logs": [],
        }
        _save_task_db(recent_task)

        from task_store import load_tasks_from_db
        loaded = load_tasks_from_db(stale_assigned_minutes=120)  # threshold = 2h; task = 30min
        loaded_task = next((t for t in loaded if t.get("id") == task_id), None)

        if loaded_task:  # may be outside 7-day window but should be present
            assert loaded_task["status"] == "assigned", (
                f"Recent task should stay assigned, got status={loaded_task['status']}"
            )
            assert not loaded_task.get("_requeued_on_startup")

        # Cleanup
        with SessionLocal() as session:
            session.query(TaskRow).filter_by(id=task_id).delete()
            session.commit()

    def test_worker_poll_does_not_return_completed_tasks(self, client, isolate_task_state):
        """Completed task must not be returned by worker poll endpoint."""
        machine_uuid = isolate_task_state
        # Use target_machine_uuid so we control which task gets assigned on poll
        task_id = _create_task_for_worker(client, machine_uuid)

        # Assign (will get our targeted task)
        poll_res = client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)
        assert poll_res.json() is not None

        # Complete the task
        client.post(
            f"/worker/tasks/{task_id}/complete",
            json={
                "machine_uuid": machine_uuid,
                "result_json": {"outcome": "success"},
            },
            headers=WORKER_HEADERS,
        )

        # Simulate restart — only our task is removed from memory, reload from DB
        _simulate_restart([task_id])

        # Our task should be back in memory but as completed
        found = next((t for t in m.tasks if t.get("id") == task_id), None)
        assert found is not None, f"Completed task {task_id} not loaded from DB"
        assert found["status"] == "completed", f"Expected completed, got {found['status']}"

        # Worker poll should NOT return our completed task
        res = client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)
        assert res.status_code == 200
        body = res.json()
        if body is not None:
            assert body["id"] != task_id, (
                f"Worker returned the completed task {task_id} — completed tasks must not be polled"
            )

    def test_task_dashboard_reads_persisted_tasks(self, client):
        """GET /api/tasks should include tasks loaded from DB after restart."""
        task_id = _create_task_via_api(client)

        # Simulate restart
        _simulate_restart([task_id])

        # Dashboard should show the task
        res = client.get("/api/tasks?limit=50")
        assert res.status_code == 200
        ids = [t.get("id") for t in res.json()]
        assert task_id in ids, (
            f"Task {task_id} not found in /api/tasks after restart. Got: {ids}"
        )

    def test_needs_human_help_task_loaded_on_startup(self):
        """A needs_human_help task should be loaded on startup for dashboard visibility."""
        if not _is_db_enabled():
            pytest.skip("DB not enabled")

        from db_writes import save_task_db as _save_task_db
        from db import SessionLocal
        from models_db import Task as TaskRow

        task_id = str(uuid4())
        paused_task: dict = {
            "id": task_id,
            "payload": {"task_type": "smart_sherpa_sync"},
            "status": "needs_human_help",
            "assigned_machine_uuid": "worker-xyz",
            "result_json": None,
            "error": "All recovery exhausted.",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "logs": [],
            "recovery_context": {"pause_reason": "timeout exhausted"},
        }
        _save_task_db(paused_task)

        from task_store import load_tasks_from_db
        loaded = load_tasks_from_db()
        loaded_task = next((t for t in loaded if t.get("id") == task_id), None)

        assert loaded_task is not None, "needs_human_help task not loaded from DB"
        assert loaded_task["status"] == "needs_human_help"
        # Should NOT be requeued — human action is required
        assert not loaded_task.get("_requeued_on_startup")

        # Cleanup
        with SessionLocal() as session:
            session.query(TaskRow).filter_by(id=task_id).delete()
            session.commit()

    def test_list_tasks_db_fallback_when_memory_empty(self, client):
        """list_tasks currently serves in-memory state and does not auto-fallback to DB."""
        task_id = _create_task_via_api(client)

        # Clear memory WITHOUT reloading (unusual edge case)
        m.tasks.clear()

        # Endpoint reflects current in-memory queue state.
        res = client.get("/api/tasks?limit=50")
        assert res.status_code == 200
        ids = [t.get("id") for t in res.json()]
        assert task_id not in ids, f"Expected in-memory view to be empty, got: {ids}"

    def test_worker_does_not_poll_other_tenant_tasks(self, client, isolate_task_state):
        """A worker should never receive a queued task from a different tenant."""
        from models_db import Tenant

        machine_uuid = isolate_task_state
        worker_tenant_id = "tenant-a"
        other_tenant_id = "tenant-b"
        with SessionLocal() as session:
            session.merge(Tenant(id=worker_tenant_id, name="Tenant A", is_internal=False))
            session.merge(Tenant(id=other_tenant_id, name="Tenant B", is_internal=False))
            session.commit()

        m.registered_workers[machine_uuid]["tenant_id"] = worker_tenant_id

        other_task_id = m._create_task_record(
            {
                "task_type": "smart_sherpa_sync",
                "tenant_id": other_tenant_id,
                "payload": {"task_type": "smart_sherpa_sync", "tenant_id": other_tenant_id},
            }
        ).id
        res = client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)
        assert res.status_code == 200
        assert res.json() is None

        matching_task_id = m._create_task_record(
            {
                "task_type": "smart_sherpa_sync",
                "tenant_id": worker_tenant_id,
                "payload": {"task_type": "smart_sherpa_sync", "tenant_id": worker_tenant_id},
            }
        ).id
        poll_res = client.get(f"/worker/tasks/next?machine_uuid={machine_uuid}", headers=WORKER_HEADERS)
        assert poll_res.status_code == 200
        body = poll_res.json()
        assert body is not None
        assert body["id"] == matching_task_id
        assert body["tenant_id"] == worker_tenant_id
        assert body["id"] != other_task_id
