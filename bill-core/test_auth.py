import importlib
import logging

import pytest
from fastapi.testclient import TestClient

import auth
import main as m
from auth import validate_auth_configuration
from db import Base, SessionLocal, engine
from models_db import Tenant
from user_auth import create_user_account


@pytest.fixture()
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILL_CORE_AUTH_ENABLED", "true")
    monkeypatch.setenv("BILL_CORE_DASHBOARD_API_KEY", "dashboard-test-key")
    monkeypatch.setenv("BILL_CORE_WORKER_SHARED_SECRET", "worker-test-secret")
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "false")


@pytest.fixture(autouse=True)
def clean_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        session.query(Tenant).delete()
        session.add(Tenant(id="default", name="Internal", is_internal=True))
        session.commit()
    yield


@pytest.fixture()
def client(auth_env: None) -> TestClient:
    importlib.reload(auth)
    importlib.reload(m)
    with TestClient(m.app) as test_client:
        yield test_client


def test_health_public_without_auth(client: TestClient, auth_env: None) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_dashboard_protected_rejects_missing_key(client: TestClient, auth_env: None) -> None:
    res = client.get("/api/system")
    assert res.status_code == 401
    assert "Missing required header" in str(res.json().get("detail"))


def test_dashboard_protected_key_only_still_requires_login(client: TestClient, auth_env: None) -> None:
    res = client.get("/api/system", headers={"X-Bill-Core-Key": "dashboard-test-key"})
    assert res.status_code == 401
    assert "Login required" in str(res.json().get("detail"))


def test_dashboard_protected_accepts_key_with_login_session(client: TestClient, auth_env: None) -> None:
    create_user_account(
        {
            "email": "admin-auth@bill.test",
            "name": "Auth Admin",
            "password": "TestPass123!",
            "role": "admin",
            "status": "active",
            "tenant_id": "default",
        }
    )
    login = client.post(
        "/api/auth/login",
        json={"email": "admin-auth@bill.test", "password": "TestPass123!"},
        headers={"X-Bill-Core-Key": "dashboard-test-key"},
    )
    assert login.status_code == 200

    res = client.get("/api/system", headers={"X-Bill-Core-Key": "dashboard-test-key"})
    assert res.status_code == 200
    assert "backend" in res.json()


def test_worker_register_rejects_missing_key(client: TestClient, auth_env: None) -> None:
    payload = {
        "machine_name": "auth-test-worker",
        "machine_uuid": "auth-test-worker-uuid",
        "tenant_id": "default",
        "worker_version": "0.0.0",
        "execution_mode": "interactive_visible",
    }
    res = client.post("/worker/register", json=payload)
    assert res.status_code == 401
    assert "Missing required header" in str(res.json().get("detail"))


def test_worker_register_accepts_correct_key(client: TestClient, auth_env: None) -> None:
    payload = {
        "machine_name": "auth-test-worker",
        "machine_uuid": "auth-test-worker-uuid-2",
        "tenant_id": "default",
        "worker_version": "0.0.0",
        "execution_mode": "interactive_visible",
    }
    res = client.post(
        "/worker/register",
        json=payload,
        headers={"X-Bill-Worker-Key": "worker-test-secret"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body.get("machine_uuid") == payload["machine_uuid"]


def test_worker_auto_update_kill_switch_keeps_worker_flows_running(
    client: TestClient,
    auth_env: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BILL_WORKER_AUTO_UPDATE_ENABLED", "false")

    payload = {
        "machine_name": "auto-update-off-worker",
        "machine_uuid": "auto-update-off-worker-uuid",
        "tenant_id": "default",
        "worker_version": "0.3.33",
        "execution_mode": "interactive_visible",
    }
    headers = {"X-Bill-Worker-Key": "worker-test-secret"}

    register = client.post("/worker/register", json=payload, headers=headers)
    assert register.status_code == 200, register.text
    register_body = register.json()
    update = register_body["update"]
    assert register_body["connection_confirmed"] is True
    assert update["update_available"] is False
    assert update["latest_version"] is None
    assert update["package_url"] is None

    heartbeat = client.post(
        "/worker/heartbeat",
        json={
            "machine_name": payload["machine_name"],
            "machine_uuid": payload["machine_uuid"],
            "tenant_id": payload["tenant_id"],
            "status": "idle",
            "worker_version": payload["worker_version"],
        },
        headers=headers,
    )
    assert heartbeat.status_code == 200, heartbeat.text

    task_poll = client.get(
        "/worker/tasks/next",
        params={"machine_uuid": payload["machine_uuid"]},
        headers=headers,
    )
    assert task_poll.status_code == 200, task_poll.text
    assert task_poll.json() is None

    update_check = client.get(
        "/worker/update/check",
        params={"machine_uuid": payload["machine_uuid"], "current_version": payload["worker_version"]},
        headers=headers,
    )
    assert update_check.status_code == 200, update_check.text
    check_body = update_check.json()
    assert check_body["update_available"] is False
    assert check_body["latest_version"] is None
    assert check_body["package_url"] is None


def test_wrong_keys_rejected(client: TestClient, auth_env: None) -> None:
    dashboard = client.get("/api/system", headers={"X-Bill-Core-Key": "wrong-key"})
    assert dashboard.status_code == 403

    worker_payload = {
        "machine_name": "auth-test-worker",
        "machine_uuid": "auth-test-worker-uuid-3",
        "tenant_id": "default",
        "worker_version": "0.0.0",
        "execution_mode": "interactive_visible",
    }
    worker = client.post(
        "/worker/register",
        json=worker_payload,
        headers={"X-Bill-Worker-Key": "wrong-key"},
    )
    assert worker.status_code == 403


def test_local_dev_bypass_only_when_enabled(monkeypatch: pytest.MonkeyPatch, auth_env: None) -> None:
    # Explicitly disabled local bypass -> missing dashboard key is rejected.
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "false")
    importlib.reload(auth)
    importlib.reload(m)
    strict_client = TestClient(m.app, base_url="http://localhost")
    strict = strict_client.get("/api/system", headers={"X-Forwarded-For": "127.0.0.1"})
    assert strict.status_code == 401
    assert "Missing required header" in str(strict.json().get("detail"))

    # Explicitly enabled local bypass -> key check is bypassed, but user session is still required.
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "true")
    importlib.reload(auth)
    importlib.reload(m)
    relaxed_client = TestClient(m.app, base_url="http://localhost")
    relaxed = relaxed_client.get("/api/system", headers={"X-Forwarded-For": "127.0.0.1"})
    assert relaxed.status_code == 401
    assert "Login required" in str(relaxed.json().get("detail"))

    # With local bypass and a valid user session, /api/system succeeds without dashboard key.
    create_user_account(
        {
            "email": "local-bypass-admin@bill.test",
            "name": "Local Bypass Admin",
            "password": "TestPass123!",
            "role": "admin",
            "status": "active",
            "tenant_id": "default",
        }
    )
    login = relaxed_client.post(
        "/api/auth/login",
        json={"email": "local-bypass-admin@bill.test", "password": "TestPass123!"},
        headers={"X-Bill-Core-Key": "dashboard-test-key", "X-Forwarded-For": "127.0.0.1"},
    )
    assert login.status_code == 200
    relaxed_authed = relaxed_client.get("/api/system", headers={"X-Forwarded-For": "127.0.0.1"})
    assert relaxed_authed.status_code == 200


def test_rejected_logs_do_not_include_secrets(
    client: TestClient,
    auth_env: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="bill-core.auth")

    provided = "do-not-log-this-provided-secret"
    client.get("/api/system", headers={"X-Bill-Core-Key": provided})

    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "dashboard-test-key" not in log_text
    assert "worker-test-secret" not in log_text
    assert provided not in log_text


def test_auth_enabled_missing_dashboard_key_fails_startup_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILL_CORE_AUTH_ENABLED", "true")
    monkeypatch.delenv("BILL_CORE_DASHBOARD_API_KEY", raising=False)
    monkeypatch.setenv("BILL_CORE_WORKER_SHARED_SECRET", "worker-test-secret")

    with pytest.raises(RuntimeError, match="Auth enabled but BILL_CORE_DASHBOARD_API_KEY is missing"):
        validate_auth_configuration()


def test_auth_enabled_missing_worker_secret_fails_startup_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILL_CORE_AUTH_ENABLED", "true")
    monkeypatch.setenv("BILL_CORE_DASHBOARD_API_KEY", "dashboard-test-key")
    monkeypatch.delenv("BILL_CORE_WORKER_SHARED_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="Auth enabled but BILL_CORE_WORKER_SHARED_SECRET is missing"):
        validate_auth_configuration()
