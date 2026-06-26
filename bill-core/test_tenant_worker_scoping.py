from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

import auth
import main as m
from db import Base, SessionLocal, engine
from models_db import Tenant
from user_auth import create_user_account


WORKER_HEADERS = {"X-Bill-Worker-Key": "worker-test-secret"}


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
        session.commit()

    m.tasks.clear()
    m.registered_workers.clear()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(m.app) as test_client:
        yield test_client


def _seed_tenant(tenant_id: str, name: str) -> None:
    with SessionLocal() as session:
        session.merge(Tenant(id=tenant_id, name=name, is_internal=False))
        session.commit()


def _make_user(email: str, role: str, tenant_id: str = "default", password: str = "Password1!") -> dict[str, Any]:
    return create_user_account(
        {
            "name": f"{role}-{tenant_id}",
            "email": email,
            "password": password,
            "role": role,
            "status": "active",
            "tenant_id": tenant_id,
        }
    )


def _login(client: TestClient, email: str, password: str = "Password1!") -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


def _register_worker(client: TestClient, machine_uuid: str, tenant_id: str) -> None:
    payload = {
        "machine_name": f"worker-{machine_uuid}",
        "machine_uuid": machine_uuid,
        "tenant_id": tenant_id,
        "worker_version": "0.0.1",
        "execution_mode": "interactive_visible",
    }
    response = client.post("/worker/register", json=payload, headers=WORKER_HEADERS)
    assert response.status_code == 200, response.text


def test_worker_register_and_heartbeat_are_tenant_bound(client: TestClient) -> None:
    _seed_tenant("tenant-a", "Tenant A")
    _seed_tenant("tenant-b", "Tenant B")

    _register_worker(client, "worker-a", "tenant-a")

    ok_heartbeat = client.post(
        "/worker/heartbeat",
        json={
            "machine_name": "worker-a",
            "machine_uuid": "worker-a",
            "tenant_id": "tenant-a",
            "status": "idle",
            "worker_version": "0.0.1",
        },
        headers=WORKER_HEADERS,
    )
    assert ok_heartbeat.status_code == 200, ok_heartbeat.text

    wrong_tenant = client.post(
        "/worker/heartbeat",
        json={
            "machine_name": "worker-a",
            "machine_uuid": "worker-a",
            "tenant_id": "tenant-b",
            "status": "idle",
            "worker_version": "0.0.1",
        },
        headers=WORKER_HEADERS,
    )
    assert wrong_tenant.status_code == 409
    assert "tenant-a" in wrong_tenant.text



def test_worker_task_poll_only_returns_same_tenant_tasks(client: TestClient) -> None:
    _seed_tenant("tenant-a", "Tenant A")
    _seed_tenant("tenant-b", "Tenant B")

    _register_worker(client, "worker-a", "tenant-a")

    other_task = m._create_task_record(
        {
            "task_type": "smart_sherpa_sync",
            "tenant_id": "tenant-b",
            "payload": {"task_type": "smart_sherpa_sync", "tenant_id": "tenant-b"},
        }
    )
    own_task = m._create_task_record(
        {
            "task_type": "smart_sherpa_sync",
            "tenant_id": "tenant-a",
            "payload": {"task_type": "smart_sherpa_sync", "tenant_id": "tenant-a"},
        }
    )

    poll = client.get("/worker/tasks/next", params={"machine_uuid": "worker-a"}, headers=WORKER_HEADERS)
    assert poll.status_code == 200, poll.text
    body = poll.json()
    assert body is not None
    assert body["id"] == own_task.id
    assert body["id"] != other_task.id
    assert body["tenant_id"] == "tenant-a"



def test_super_admin_and_tenant_admin_worker_visibility_and_management(client: TestClient) -> None:
    _seed_tenant("tenant-a", "Tenant A")
    _seed_tenant("tenant-b", "Tenant B")

    _register_worker(client, "worker-a", "tenant-a")
    _register_worker(client, "worker-b", "tenant-b")

    _make_user("super@bill.test", "super_admin", tenant_id="default")
    _make_user("admin-a@bill.test", "admin", tenant_id="tenant-a")
    _make_user("admin-b@bill.test", "admin", tenant_id="tenant-b")

    _login(client, "super@bill.test")
    all_workers = client.get("/api/super-admin/workers")
    assert all_workers.status_code == 200, all_workers.text
    tenant_ids = {item.get("tenant_id") for item in all_workers.json().get("workers", [])}
    assert {"tenant-a", "tenant-b"}.issubset(tenant_ids)

    scoped_super = client.get("/api/super-admin/tenants/tenant-a/workers")
    assert scoped_super.status_code == 200, scoped_super.text
    assert all(item.get("tenant_id") == "tenant-a" for item in scoped_super.json().get("workers", []))

    _login(client, "admin-a@bill.test")

    own_workers = client.get("/api/admin/tenants/tenant-a/workers")
    assert own_workers.status_code == 200, own_workers.text
    own_worker_ids = {item.get("machine_uuid") for item in own_workers.json().get("workers", [])}
    assert "worker-a" in own_worker_ids
    assert "worker-b" not in own_worker_ids

    cross_tenant_workers = client.get("/api/admin/tenants/tenant-b/workers")
    assert cross_tenant_workers.status_code == 403

    rename_own = client.patch(
        "/api/admin/tenants/tenant-a/workers/worker-a/name",
        json={"machine_name": "tenant-a-renamed"},
    )
    assert rename_own.status_code == 200, rename_own.text

    rename_other = client.patch(
        "/api/admin/tenants/tenant-a/workers/worker-b/name",
        json={"machine_name": "should-fail"},
    )
    assert rename_other.status_code == 404

    delete_other = client.delete("/api/admin/tenants/tenant-a/workers/worker-b")
    assert delete_other.status_code == 404

    delete_own = client.delete("/api/admin/tenants/tenant-a/workers/worker-a")
    assert delete_own.status_code == 200, delete_own.text

    _login(client, "admin-b@bill.test")
    tenant_b_workers = client.get("/api/admin/tenants/tenant-b/workers")
    assert tenant_b_workers.status_code == 200, tenant_b_workers.text
    tenant_b_ids = {item.get("machine_uuid") for item in tenant_b_workers.json().get("workers", [])}
    assert "worker-b" in tenant_b_ids
    assert "worker-a" not in tenant_b_ids
