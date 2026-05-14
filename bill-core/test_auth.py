import logging

import pytest
from fastapi.testclient import TestClient

import main as m
from auth import validate_auth_configuration


@pytest.fixture()
def auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BILL_CORE_AUTH_ENABLED", "true")
    monkeypatch.setenv("BILL_CORE_DASHBOARD_API_KEY", "dashboard-test-key")
    monkeypatch.setenv("BILL_CORE_WORKER_SHARED_SECRET", "worker-test-secret")
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "false")


@pytest.fixture()
def client() -> TestClient:
    return TestClient(m.app)


def test_health_public_without_auth(client: TestClient, auth_env: None) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("status") == "ok"


def test_dashboard_protected_rejects_missing_key(client: TestClient, auth_env: None) -> None:
    res = client.get("/api/system")
    assert res.status_code == 401
    assert "Missing required header" in str(res.json().get("detail"))


def test_dashboard_protected_accepts_correct_key(client: TestClient, auth_env: None) -> None:
    res = client.get("/api/system", headers={"X-Bill-Core-Key": "dashboard-test-key"})
    assert res.status_code == 200
    assert "backend" in res.json()


def test_worker_register_rejects_missing_key(client: TestClient, auth_env: None) -> None:
    payload = {
        "machine_name": "auth-test-worker",
        "machine_uuid": "auth-test-worker-uuid",
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


def test_wrong_keys_rejected(client: TestClient, auth_env: None) -> None:
    dashboard = client.get("/api/system", headers={"X-Bill-Core-Key": "wrong-key"})
    assert dashboard.status_code == 403

    worker_payload = {
        "machine_name": "auth-test-worker",
        "machine_uuid": "auth-test-worker-uuid-3",
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
    # Explicitly disabled local bypass -> localhost request must still require auth.
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "false")
    strict_client = TestClient(m.app, base_url="http://localhost")
    strict = strict_client.get("/api/system", headers={"X-Forwarded-For": "127.0.0.1"})
    assert strict.status_code == 401

    # Explicitly enabled local bypass -> localhost request can pass without auth header.
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "true")
    relaxed_client = TestClient(m.app, base_url="http://localhost")
    relaxed = relaxed_client.get("/api/system", headers={"X-Forwarded-For": "127.0.0.1"})
    assert relaxed.status_code == 200


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
