from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import auth
import main as m
from batch_runner_service import compute_dashboard_summary
from db import Base, SessionLocal, engine
from models_db import Tenant
from user_auth import create_user_account


@pytest.fixture(autouse=True)
def isolate_state(monkeypatch: pytest.MonkeyPatch) -> None:
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
        session.add(Tenant(id="tenant-a", name="Tenant A", is_internal=False))
        session.add(Tenant(id="tenant-b", name="Tenant B", is_internal=False))
        session.commit()

    m.tasks.clear()
    m.registered_workers.clear()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(m.app) as test_client:
        yield test_client


def _login_as(client: TestClient, email: str, role: str, tenant_id: str) -> None:
    create_user_account(
        {
            "email": email,
            "name": f"{role}-{tenant_id}",
            "password": "Password1!",
            "role": role,
            "status": "active",
            "tenant_id": tenant_id,
        }
    )
    response = client.post("/api/auth/login", json={"email": email, "password": "Password1!"})
    assert response.status_code == 200, response.text


def _register_worker(machine_uuid: str, tenant_id: str) -> None:
    m.registered_workers[machine_uuid] = {
        "machine_uuid": machine_uuid,
        "machine_name": machine_uuid,
        "token": f"token-{machine_uuid}",
        "tenant_id": tenant_id,
        "status": "idle",
        "worker_version": "0.0.1",
        "execution_mode": "interactive_visible",
        "last_seen": "2099-01-01T00:00:00",
    }


def _install_fake_run_tenant_workflow(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run_tenant_workflow(tenant_id: str, workflow_id: str, input_data: dict[str, Any]):
        payload = dict(input_data)
        payload.setdefault("tenant_id", tenant_id)
        payload.setdefault("workflow_id", workflow_id)
        payload.setdefault("workflow_name", workflow_id)
        queued_task = m._create_task_record(payload)
        return SimpleNamespace(queued_task=queued_task)

    monkeypatch.setattr(m, "run_tenant_workflow", _fake_run_tenant_workflow)


def test_batch_upload_start_and_export(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-a@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")
    _install_fake_run_tenant_workflow(monkeypatch)

    csv_content = (
        "member_name,member_id,paid_through_date\n"
        "Jane Doe,123,2030-01-31\n"
        "John Smith,124,2030-01-15\n"
    )

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={"spreadsheet": ("ci-checks.csv", csv_content, "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    assert body["batch"]["tenant_id"] == "tenant-a"
    assert body["batch"]["summary"]["total"] == 2

    batch_id = body["batch"]["batch_id"]

    start = client.post(f"/api/batch-runs/{batch_id}/start")
    assert start.status_code == 200, start.text
    start_body = start.json()
    assert start_body["queued_rows"] == 2

    rows = client.get(f"/api/batch-runs/{batch_id}/rows")
    assert rows.status_code == 200, rows.text
    rows_body = rows.json()
    assert rows_body["total_rows"] == 2
    assert all(r["child_task_id"] for r in rows_body["rows"])
    first_row = rows_body["rows"][0]
    assert "task_id" in first_row
    assert "assigned_machine_uuid" in first_row
    assert "worker_name" in first_row
    assert "keap_task_created" in first_row

    export = client.get(f"/api/batch-runs/{batch_id}/export")
    assert export.status_code == 200, export.text
    assert "row_number,member_name,member_id" in export.text


def test_batch_selected_worker_never_creates_unassigned_tasks(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-a2@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")
    _install_fake_run_tenant_workflow(monkeypatch)

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={
            "spreadsheet": (
                "ci-checks.csv",
                "member_name,member_id,paid_through_date\nAlice,001,2030-01-31\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["batch_id"]

    start = client.post(f"/api/batch-runs/{batch_id}/start")
    assert start.status_code == 200, start.text

    assert len(m.tasks) >= 1
    for task in m.tasks:
        assert task.get("assigned_machine_uuid") == "worker-a"
        payload = dict(task.get("payload") or {})
        assert payload.get("target_machine_uuid") == "worker-a"


def test_batch_upload_denies_cross_tenant_worker_access(client: TestClient) -> None:
    _login_as(client, "admin-b@bill.test", "admin", "tenant-b")
    _register_worker("worker-a", "tenant-a")

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={
            "spreadsheet": (
                "ci-checks.csv",
                "member_name,member_id,paid_through_date\nAlice,001,2030-01-31\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 403, upload.text


def test_batch_list_returns_recent_batches(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-list@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")
    _install_fake_run_tenant_workflow(monkeypatch)

    first = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={"spreadsheet": ("one.csv", "member_name,member_id,paid_through_date\nA,1,2030-01-31\n", "text/csv")},
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={"spreadsheet": ("two.csv", "member_name,member_id,paid_through_date\nB,2,2030-01-31\n", "text/csv")},
    )
    assert second.status_code == 200, second.text

    listing = client.get("/api/batch-runs?limit=5")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["count"] >= 2
    ids = [item["batch_id"] for item in body["items"]]
    assert second.json()["batch"]["batch_id"] in ids
    assert first.json()["batch"]["batch_id"] in ids


def test_batch_summary_has_progress_and_eta_fields(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-summary@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")
    _install_fake_run_tenant_workflow(monkeypatch)

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={
            "spreadsheet": (
                "summary.csv",
                "member_name,member_id,paid_through_date\nA,1,2030-01-31\nB,2,2030-01-20\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["batch_id"]

    start = client.post(f"/api/batch-runs/{batch_id}/start")
    assert start.status_code == 200, start.text

    batch = client.get(f"/api/batch-runs/{batch_id}")
    assert batch.status_code == 200, batch.text
    summary = batch.json()["summary"]

    assert summary["total_rows"] == 2
    assert "progress_percent" in summary
    assert isinstance(summary["progress_percent"], int)
    assert summary["estimated_remaining_seconds"] is None or isinstance(summary["estimated_remaining_seconds"], int)


def test_batch_rows_filter_by_failed(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-filter@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")

    def _fake_run_tenant_workflow(tenant_id: str, workflow_id: str, input_data: dict[str, Any]):
        payload = dict(input_data)
        payload.setdefault("tenant_id", tenant_id)
        payload.setdefault("workflow_id", workflow_id)
        payload.setdefault("workflow_name", workflow_id)
        queued_task = m._create_task_record(payload)
        task = next((t for t in m.tasks if t.get("id") == queued_task.id), None)
        if task and str((payload.get("source_record") or {}).get("client_name") or "") == "B":
            task["status"] = "failed"
            task["error"] = "simulated failure"
        return SimpleNamespace(queued_task=queued_task)

    monkeypatch.setattr(m, "run_tenant_workflow", _fake_run_tenant_workflow)

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={
            "spreadsheet": (
                "filter.csv",
                "member_name,member_id,paid_through_date\nA,1,2030-01-31\nB,2,2030-01-20\n",
                "text/csv",
            )
        },
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["batch_id"]

    start = client.post(f"/api/batch-runs/{batch_id}/start")
    assert start.status_code == 200, start.text

    failed_rows = client.get(f"/api/batch-runs/{batch_id}/rows?status_filter=failed")
    assert failed_rows.status_code == 200, failed_rows.text
    rows = failed_rows.json()["rows"]
    assert len(rows) >= 1
    assert all(str(row["status"]).lower() == "failed" for row in rows)


def test_cancel_preserves_batch_history(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-cancel@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")
    _install_fake_run_tenant_workflow(monkeypatch)

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={"spreadsheet": ("cancel.csv", "member_name,member_id,paid_through_date\nA,1,2030-01-31\n", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["batch_id"]

    start = client.post(f"/api/batch-runs/{batch_id}/start")
    assert start.status_code == 200, start.text

    cancel = client.post(f"/api/batch-runs/{batch_id}/cancel")
    assert cancel.status_code == 200, cancel.text

    still_exists = client.get(f"/api/batch-runs/{batch_id}")
    assert still_exists.status_code == 200, still_exists.text
    assert still_exists.json()["status"] == "canceled"


def test_retry_failed_preserves_batch_id(monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    _login_as(client, "admin-retry@bill.test", "admin", "tenant-a")
    _register_worker("worker-a", "tenant-a")

    first_call = {"seen": False}

    def _fake_run_tenant_workflow(tenant_id: str, workflow_id: str, input_data: dict[str, Any]):
        payload = dict(input_data)
        payload.setdefault("tenant_id", tenant_id)
        payload.setdefault("workflow_id", workflow_id)
        payload.setdefault("workflow_name", workflow_id)
        queued_task = m._create_task_record(payload)
        task = next((t for t in m.tasks if t.get("id") == queued_task.id), None)
        if task and not first_call["seen"]:
            task["status"] = "failed"
            task["error"] = "temporary failure"
            first_call["seen"] = True
        return SimpleNamespace(queued_task=queued_task)

    monkeypatch.setattr(m, "run_tenant_workflow", _fake_run_tenant_workflow)

    upload = client.post(
        "/api/batch-runs/upload",
        data={
            "workflow_name": "ci_checks",
            "target_machine_uuid": "worker-a",
            "column_mapping": '{"member_name":"member_name","member_id":"member_id","paid_through_date":"paid_through_date"}',
        },
        files={"spreadsheet": ("retry.csv", "member_name,member_id,paid_through_date\nA,1,2030-01-31\n", "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    batch_id = upload.json()["batch"]["batch_id"]

    start = client.post(f"/api/batch-runs/{batch_id}/start")
    assert start.status_code == 200, start.text

    retry = client.post(f"/api/batch-runs/{batch_id}/retry-failed")
    assert retry.status_code == 200, retry.text
    assert retry.json()["batch_id"] == batch_id

    after = client.get(f"/api/batch-runs/{batch_id}")
    assert after.status_code == 200, after.text
    assert after.json()["batch_id"] == batch_id


def test_compute_dashboard_summary_progress_and_eta_when_insufficient_data() -> None:
    rows = [
        {
            "status": "completed",
            "payment_status": "good",
            "keap_task_created": False,
            "completed_at": None,
        },
        {
            "status": "ready",
            "payment_status": "needs_review",
            "keap_task_created": False,
            "completed_at": None,
        },
    ]
    summary = compute_dashboard_summary(rows)
    assert summary["total_rows"] == 2
    assert summary["completed_rows"] == 1
    assert summary["pending_rows"] == 1
    assert summary["progress_percent"] == 50
    assert summary["estimated_remaining_seconds"] is None
