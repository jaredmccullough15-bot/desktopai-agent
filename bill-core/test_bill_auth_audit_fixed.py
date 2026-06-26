"""
test_bill_auth_audit.py — Targeted tests for Bill user auth, session lifecycle,
role enforcement, audit log recording, and payload redaction.

Strategy: Use TestClient with request monkeypatching to test FastAPI endpoints
without needing full app startup. Tests validate auth middleware, login/logout,
role enforcement, and audit recording.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from user_auth import (
    create_user_account,
    hash_password,
    hash_session_token,
    login_user,
    record_audit_event,
    resolve_current_user,
    _redact_payload,
)
from models_db import UserAccount, UserSession, AuditLogEntry, Tenant
from db import SessionLocal



# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_db():
    """Clean up the default SQLite DB before each test."""
    import db
    # Delete any existing tables
    db.Base.metadata.drop_all(bind=db.engine)
    # Recreate all tables fresh
    db.Base.metadata.create_all(bind=db.engine)
    
    # Seed default tenant
    with SessionLocal() as s:
        s.query(Tenant).delete()
        s.add(Tenant(id="default", name="Internal", is_internal=True))
        s.commit()
    
    yield
    
    # Cleanup after test
    db.Base.metadata.drop_all(bind=db.engine)


@pytest.fixture()
def api_env(monkeypatch):
    monkeypatch.setenv("BILL_CORE_AUTH_ENABLED", "true")
    monkeypatch.setenv("BILL_CORE_DASHBOARD_API_KEY", "dashboard-test-key")
    monkeypatch.setenv("BILL_CORE_WORKER_SHARED_SECRET", "worker-test-secret")
    monkeypatch.setenv("BILL_CORE_AUTH_ALLOW_LOCAL_DEV", "false")


@pytest.fixture()
def client(api_env, clean_db):
    """TestClient using the clean DB."""
    import main
    return TestClient(main.app, raise_server_exceptions=True)


def _create_test_user(
    email: str = "test@bill.test",
    password: str = "TestPass123!",
    role: str = "viewer",
    status: str = "active",
) -> dict[str, Any]:
    return create_user_account(
        {
            "email": email,
            "name": f"Test {role.capitalize()}",
            "password": password,
            "role": role,
            "status": status,
            "tenant_id": "default",
        }
    )


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    """Login and return a header dict with the session cookie."""
    res = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
        headers={"X-Bill-Core-Key": "dashboard-test-key"},
    )
    assert res.status_code == 200, res.text
    cookie = res.cookies.get("bill_core_session")
    return {"Cookie": f"bill_core_session={cookie}"}


# ---------------------------------------------------------------------------
# 1. Login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success_returns_user_and_cookie(self, client):
        _create_test_user(email="admin@bill.test", role="admin")
        res = client.post(
            "/api/auth/login",
            json={"email": "admin@bill.test", "password": "TestPass123!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["user"]["email"] == "admin@bill.test"
        assert body["user"]["role"] == "admin"
        assert "session_expires_at" in body
        assert "bill_core_session" in res.cookies

    def test_login_failure_wrong_password(self, client):
        _create_test_user(isolate_db, email="user@bill.test")
        res = client.post(
            "/api/auth/login",
            json={"email": "user@bill.test", "password": "WrongPass!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 401
        assert "Invalid" in res.json().get("detail", "")

    def test_login_failure_unknown_email(self, client):
        res = client.post(
            "/api/auth/login",
            json={"email": "nobody@bill.test", "password": "AnyPass!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 401

    def test_login_fails_inactive_user(self, client):
        _create_test_user(isolate_db, email="inactive@bill.test", status="inactive")
        res = client.post(
            "/api/auth/login",
            json={"email": "inactive@bill.test", "password": "TestPass123!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 401

    def test_login_fails_missing_password(self, client):
        res = client.post(
            "/api/auth/login",
            json={"email": "any@bill.test", "password": ""},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code in {400, 401, 422}


# ---------------------------------------------------------------------------
# 2. /api/auth/me
# ---------------------------------------------------------------------------

class TestAuthMe:
    def test_me_returns_user_when_logged_in(self, client):
        _create_test_user(isolate_db, email="me@bill.test", role="runner")
        headers = _auth_headers(client, "me@bill.test", "TestPass123!")
        headers["X-Bill-Core-Key"] = "dashboard-test-key"
        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 200
        assert res.json()["user"]["email"] == "me@bill.test"

    def test_me_returns_401_without_session(self, client):
        res = client.get(
            "/api/auth/me",
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 401

    def test_me_returns_401_for_expired_session(self, client):
        _create_test_user(isolate_db, email="expire@bill.test")
        # Login to get a session token
        login_res = client.post(
            "/api/auth/login",
            json={"email": "expire@bill.test", "password": "TestPass123!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        cookie = login_res.cookies.get("bill_core_session")

        # Manually expire the session in the DB
        from models_db import UserSession
        token_hash = hash_session_token(cookie)
        with isolate_db() as session:
            row = session.query(UserSession).filter_by(session_token_hash=token_hash).first()
            if row:
                row.expires_at = datetime.utcnow() - timedelta(hours=1)
                session.commit()

        headers = {
            "Cookie": f"bill_core_session={cookie}",
            "X-Bill-Core-Key": "dashboard-test-key",
        }
        res = client.get("/api/auth/me", headers=headers)
        assert res.status_code == 401


# ---------------------------------------------------------------------------
# 3. Logout
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_revokes_session(self, client):
        _create_test_user(isolate_db, email="logout@bill.test")
        auth = _auth_headers(client, "logout@bill.test", "TestPass123!")
        auth["X-Bill-Core-Key"] = "dashboard-test-key"

        # Confirm session works first
        assert client.get("/api/auth/me", headers=auth).status_code == 200

        # Logout
        client.post("/api/auth/logout", headers=auth)

        # Session should now be invalid
        assert client.get("/api/auth/me", headers=auth).status_code == 401

    def test_logout_without_session_is_safe(self, client):
        res = client.post(
            "/api/auth/logout",
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 200


# ---------------------------------------------------------------------------
# 4. Role restrictions
# ---------------------------------------------------------------------------

class TestRoleRestrictions:
    def _admin_session(self, client):
        _create_test_user(isolate_db, email="admin-role@bill.test", role="admin")
        h = _auth_headers(client, "admin-role@bill.test", "TestPass123!")
        h["X-Bill-Core-Key"] = "dashboard-test-key"
        return h

    def _viewer_session(self, client):
        _create_test_user(isolate_db, email="viewer-role@bill.test", role="viewer")
        h = _auth_headers(client, "viewer-role@bill.test", "TestPass123!")
        h["X-Bill-Core-Key"] = "dashboard-test-key"
        return h

    def test_admin_can_access_admin_users(self, client):
        headers = self._admin_session(client)
        res = client.get("/api/admin/users", headers=headers)
        assert res.status_code == 200

    def test_viewer_cannot_access_admin_users(self, client):
        headers = self._viewer_session(client)
        res = client.get("/api/admin/users", headers=headers)
        assert res.status_code == 403

    def test_viewer_cannot_access_admin_audit_logs(self, client):
        headers = self._viewer_session(client)
        res = client.get("/api/admin/audit-logs", headers=headers)
        assert res.status_code == 403

    def test_admin_can_access_audit_logs(self, client):
        headers = self._admin_session(client)
        res = client.get("/api/admin/audit-logs", headers=headers)
        assert res.status_code == 200

    def test_admin_can_create_user(self, client):
        headers = self._admin_session(client)
        res = client.post(
            "/api/admin/users",
            json={
                "name": "New User",
                "email": "new@bill.test",
                "password": "NewPass123!",
                "role": "viewer",
            },
            headers=headers,
        )
        assert res.status_code == 200

    def test_viewer_cannot_create_user(self, client):
        headers = self._viewer_session(client)
        res = client.post(
            "/api/admin/users",
            json={
                "name": "Hacker",
                "email": "hacker@bill.test",
                "password": "HackerPass!",
                "role": "admin",
            },
            headers=headers,
        )
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# 5. Audit record creation
# ---------------------------------------------------------------------------

class TestAuditRecords:
    def test_login_success_creates_audit_entry(self, client):
        _create_test_user(isolate_db, email="audit-login@bill.test")
        client.post(
            "/api/auth/login",
            json={"email": "audit-login@bill.test", "password": "TestPass123!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        from models_db import AuditLogEntry
        with isolate_db() as session:
            entries = (
                session.query(AuditLogEntry)
                .filter_by(event_type="login_success")
                .all()
            )
        assert len(entries) >= 1

    def test_login_failure_creates_audit_entry(self, client):
        _create_test_user(isolate_db, email="audit-fail@bill.test")
        client.post(
            "/api/auth/login",
            json={"email": "audit-fail@bill.test", "password": "WrongPass!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        from models_db import AuditLogEntry
        with isolate_db() as session:
            entries = (
                session.query(AuditLogEntry)
                .filter_by(event_type="login_failed")
                .all()
            )
        assert len(entries) >= 1

    def test_user_created_creates_audit_entry(self, client):
        _create_test_user(isolate_db, email="admin-create@bill.test", role="admin")
        headers = _auth_headers(client, "admin-create@bill.test", "TestPass123!")
        headers["X-Bill-Core-Key"] = "dashboard-test-key"
        client.post(
            "/api/admin/users",
            json={"name": "Audit User", "email": "audited@bill.test", "password": "AuditPass1!", "role": "viewer"},
            headers=headers,
        )
        from models_db import AuditLogEntry
        with isolate_db() as session:
            entries = (
                session.query(AuditLogEntry)
                .filter_by(event_type="user_created")
                .all()
            )
        assert len(entries) >= 1


# ---------------------------------------------------------------------------
# 6. Audit payload redaction
# ---------------------------------------------------------------------------

class TestAuditRedaction:
    def test_login_audit_does_not_store_raw_password(self, client):
        _create_test_user(isolate_db, email="redact@bill.test")
        client.post(
            "/api/auth/login",
            json={"email": "redact@bill.test", "password": "SecretPassword999!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        from models_db import AuditLogEntry
        with isolate_db() as session:
            entries = session.query(AuditLogEntry).all()
        for entry in entries:
            assert "SecretPassword999!" not in (entry.details_json or "")
            assert "SecretPassword999!" not in (entry.redacted_payload or "")

    def test_record_audit_event_redacts_password_field(self):
        import user_auth
        # Patch save_audit_log_db to capture what is written
        captured: list[dict] = []

        def fake_save(payload):
            captured.append(payload)

        with patch("user_auth.save_audit_log_db", side_effect=fake_save):
            record_audit_event(
                "test_event",
                details={"email": "x@y.com"},
                redacted_payload={"email": "x@y.com", "password": "RawSecret!"},
                source="test",
            )

        assert len(captured) == 1
        stored_payload = captured[0].get("redacted_payload", {})
        assert stored_payload.get("password") == "[REDACTED]"
        assert "RawSecret!" not in str(stored_payload)


# ---------------------------------------------------------------------------
# 7. Non-user system paths exempt from user-auth requirement
# ---------------------------------------------------------------------------

class TestSystemPathExemptions:
    def test_health_requires_no_login(self, client, api_env):
        res = client.get("/health")
        assert res.status_code == 200

    def test_worker_register_requires_no_login_only_worker_key(self, client, api_env):
        """Worker registration uses X-Bill-Worker-Key, NOT user session."""
        res = client.post(
            "/worker/register",
            json={
                "machine_name": "test-worker",
                "machine_uuid": "test-uuid-exempt",
                "worker_version": "1.0.0",
                "execution_mode": "headless_background",
            },
            headers={"X-Bill-Worker-Key": "worker-test-secret"},
        )
        assert res.status_code == 200

    def test_api_auth_login_is_public(self, client, api_env):
        """Login endpoint accessible without prior auth."""
        res = client.post(
            "/api/auth/login",
            json={"email": "none@bill.test", "password": "wrong"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        # Should get 401 for bad creds, not 403 for missing user session
        assert res.status_code == 401

    def test_docs_is_public(self, client, api_env):
        res = client.get("/docs")
        assert res.status_code == 200

    def test_openapi_json_is_public(self, client, api_env):
        res = client.get("/openapi.json")
        assert res.status_code == 200
