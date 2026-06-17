"""
test_bill_auth_audit.py — Targeted tests for Bill user auth, session lifecycle,
role enforcement, audit log recording, and payload redaction.

Strategy: Use TestClient with request monkeypatching to test FastAPI endpoints
without needing full app startup. Tests validate auth middleware, login/logout,
role enforcement, and audit recording.
"""
from __future__ import annotations

import os
import threading
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock
from io import BytesIO
from urllib.parse import parse_qs, urlparse

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
    return TestClient(main.app, raise_server_exceptions=False)


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
        _create_test_user(email="user@bill.test")
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
        _create_test_user(email="inactive@bill.test", status="inactive")
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
        _create_test_user(email="me@bill.test", role="runner")
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

    def test_unauthenticated_user_cannot_access_protected_admin_route(self, client):
        res = client.get(
            "/api/admin/users",
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        assert res.status_code == 401

    def test_me_returns_401_for_expired_session(self, client):
        _create_test_user(email="expire@bill.test")
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
        with SessionLocal() as session:
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
        _create_test_user(email="logout@bill.test")
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
        _create_test_user(email="admin-role@bill.test", role="admin")
        h = _auth_headers(client, "admin-role@bill.test", "TestPass123!")
        h["X-Bill-Core-Key"] = "dashboard-test-key"
        return h

    def _viewer_session(self, client):
        _create_test_user(email="viewer-role@bill.test", role="viewer")
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

    def test_viewer_cannot_start_teaching(self, client):
        headers = self._viewer_session(client)
        # Any draft_id is fine here: middleware role-check should reject viewer before handler logic.
        res = client.post(
            "/api/brain/workflow-learning/drafts/nonexistent-draft/teach-session/start",
            json={},
            headers=headers,
        )
        assert res.status_code == 403


# ---------------------------------------------------------------------------
# 5. Audit record creation
# ---------------------------------------------------------------------------

class TestAuditRecords:
    def test_login_success_creates_audit_entry(self, client):
        _create_test_user(email="audit-login@bill.test")
        client.post(
            "/api/auth/login",
            json={"email": "audit-login@bill.test", "password": "TestPass123!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        from models_db import AuditLogEntry
        with SessionLocal() as session:
            entries = (
                session.query(AuditLogEntry)
                .filter_by(event_type="login_success")
                .all()
            )
        assert len(entries) >= 1

    def test_login_failure_creates_audit_entry(self, client):
        _create_test_user(email="audit-fail@bill.test")
        client.post(
            "/api/auth/login",
            json={"email": "audit-fail@bill.test", "password": "WrongPass!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        from models_db import AuditLogEntry
        with SessionLocal() as session:
            entries = (
                session.query(AuditLogEntry)
                .filter_by(event_type="login_failed")
                .all()
            )
        assert len(entries) >= 1

    def test_user_created_creates_audit_entry(self, client):
        _create_test_user(email="admin-create@bill.test", role="admin")
        headers = _auth_headers(client, "admin-create@bill.test", "TestPass123!")
        headers["X-Bill-Core-Key"] = "dashboard-test-key"
        client.post(
            "/api/admin/users",
            json={"name": "Audit User", "email": "audited@bill.test", "password": "AuditPass1!", "role": "viewer"},
            headers=headers,
        )
        from models_db import AuditLogEntry
        with SessionLocal() as session:
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
        _create_test_user(email="redact@bill.test")
        client.post(
            "/api/auth/login",
            json={"email": "redact@bill.test", "password": "SecretPassword999!"},
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        from models_db import AuditLogEntry
        with SessionLocal() as session:
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

    def test_worker_heartbeat_requires_no_login_only_worker_key(self, client, api_env):
        """Worker heartbeat uses X-Bill-Worker-Key, NOT user session."""
        machine_uuid = "heartbeat-test-uuid"
        register = client.post(
            "/worker/register",
            json={
                "machine_name": "heartbeat-test-worker",
                "machine_uuid": machine_uuid,
                "worker_version": "1.0.0",
                "execution_mode": "headless_background",
            },
            headers={"X-Bill-Worker-Key": "worker-test-secret"},
        )
        assert register.status_code == 200

        heartbeat = client.post(
            "/worker/heartbeat",
            json={
                "machine_name": "heartbeat-test-worker",
                "machine_uuid": machine_uuid,
                "status": "idle",
            },
            headers={"X-Bill-Worker-Key": "worker-test-secret"},
        )
        assert heartbeat.status_code == 200

    def test_extension_events_path_exempt_from_user_auth(self, client, api_env):
        """Extension-events endpoint should not fail with user-auth 401/403 when session id is unknown."""
        res = client.post(
            "/api/teaching/session/nonexistent-session-id/extension-events",
            json={
                "event_type": "input",
                "current_url": "https://example.com",
                "domain": "example.com",
            },
            headers={"X-Bill-Core-Key": "dashboard-test-key"},
        )
        # Exemption means request reaches route handler; expected app-level outcome is session-not-found (404).
        assert res.status_code == 404

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


class TestTokenizedDirectDownloadExemptions:
    def test_worker_token_download_allows_no_dashboard_header(self, client, tmp_path: Path, monkeypatch):
        import main as main_module

        pkg_dir = tmp_path / "worker-packages"
        pkg_dir.mkdir()
        with zipfile.ZipFile(pkg_dir / "bill-worker-auth.zip", "w") as zf:
            zf.writestr("BillWorker.exe", b"auth-test")

        monkeypatch.setattr(main_module, "WORKER_PACKAGES_DIR", pkg_dir)
        monkeypatch.setattr(main_module, "worker_releases", [])
        monkeypatch.setattr(main_module, "_releases_lock", threading.Lock())

        _create_test_user(email="admin_download@test.com", role="admin")
        _create_test_user(email="runner_download@test.com", role="runner")

        admin_headers = _auth_headers(client, "admin_download@test.com", "TestPass123!")
        admin_headers["X-Bill-Core-Key"] = "dashboard-test-key"
        create_resp = client.post(
            "/api/worker-releases",
            json={"version": "9.9.9", "package_filename": "bill-worker-auth.zip", "channel": "stable"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        release_id = create_resp.json()["id"]

        mark_resp = client.post(
            f"/api/worker-releases/{release_id}/mark-current",
            json={"confirm": True},
            headers=admin_headers,
        )
        assert mark_resp.status_code == 200, mark_resp.text

        runner_headers = _auth_headers(client, "runner_download@test.com", "TestPass123!")
        runner_headers["X-Bill-Core-Key"] = "dashboard-test-key"
        token_resp = client.post(
            f"/api/worker-releases/{release_id}/download-url",
            headers=runner_headers,
        )
        assert token_resp.status_code == 200, token_resp.text
        parsed = urlparse(token_resp.json()["download_url"])
        token = parse_qs(parsed.query)["token"][0]

        client.cookies.clear()
        download_resp = client.get(f"{parsed.path}?token={token}")
        assert download_resp.status_code == 200, download_resp.text
        assert download_resp.headers.get("content-type", "").startswith("application/zip")

    def test_extension_token_download_allows_no_dashboard_header(self, client, tmp_path: Path, monkeypatch):
        import main as main_module

        pkg_dir = tmp_path / "extension-packages"
        pkg_dir.mkdir()
        with zipfile.ZipFile(pkg_dir / "bill-extension-auth.zip", "w") as zf:
            zf.writestr("manifest.json", b"{}")

        monkeypatch.setattr(main_module, "EXTENSION_PACKAGES_DIR", pkg_dir)
        monkeypatch.setattr(main_module, "extension_releases", [])
        monkeypatch.setattr(main_module, "_extension_releases_lock", threading.Lock())

        _create_test_user(email="admin_ext@test.com", role="admin")
        _create_test_user(email="teacher_ext@test.com", role="teacher")

        admin_headers = _auth_headers(client, "admin_ext@test.com", "TestPass123!")
        admin_headers["X-Bill-Core-Key"] = "dashboard-test-key"
        create_resp = client.post(
            "/api/extension-releases",
            json={"version_label": "3.3.3", "file_name": "bill-extension-auth.zip"},
            headers=admin_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        release_id = create_resp.json()["id"]

        mark_resp = client.post(
            f"/api/extension-releases/{release_id}/mark-current",
            json={"confirm": True},
            headers=admin_headers,
        )
        assert mark_resp.status_code == 200, mark_resp.text

        teacher_headers = _auth_headers(client, "teacher_ext@test.com", "TestPass123!")
        teacher_headers["X-Bill-Core-Key"] = "dashboard-test-key"
        token_resp = client.post(
            f"/api/extension-releases/{release_id}/download-url",
            headers=teacher_headers,
        )
        assert token_resp.status_code == 200, token_resp.text
        parsed = urlparse(token_resp.json()["download_url"])
        token = parse_qs(parsed.query)["token"][0]

        client.cookies.clear()
        download_resp = client.get(f"{parsed.path}?token={token}")
        assert download_resp.status_code == 200, download_resp.text
        assert download_resp.headers.get("content-type", "").startswith("application/zip")

    def test_non_token_worker_download_still_requires_dashboard_header(self, client):
        res = client.get("/api/worker-releases/any-id/download")
        assert res.status_code == 401
        assert "Missing required header: X-Bill-Core-Key" in res.json().get("detail", "")

    def test_worker_release_routes_still_require_dashboard_header(self, client):
        res = client.get("/api/worker-releases/current")
        assert res.status_code == 401
        assert "Missing required header: X-Bill-Core-Key" in res.json().get("detail", "")
