"""
test_extension_release.py — Chrome Extension Download Center tests.

Run with:
    pytest test_extension_release.py -v --tb=short
"""
from __future__ import annotations

import hashlib
import os
import threading
import zipfile
from pathlib import Path
from typing import Any, Generator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from models_db import Tenant
from db import SessionLocal

os.environ.setdefault("BILL_CORE_AUTH_ENABLED", "false")


@pytest.fixture(autouse=True)
def clean_db() -> Generator[None, None, None]:
    """Drop and recreate the real DB tables before/after each test."""
    import db
    db.Base.metadata.drop_all(bind=db.engine)
    db.Base.metadata.create_all(bind=db.engine)
    with SessionLocal() as s:
        s.query(Tenant).delete()
        s.add(Tenant(id="default", name="Internal", is_internal=True))
        s.commit()
    yield
    db.Base.metadata.drop_all(bind=db.engine)


@pytest.fixture(scope="function")
def fake_package_dir(tmp_path: Path) -> Path:
    """Create a temp extension-packages dir with a dummy zip file."""
    pkg_dir = tmp_path / "extension-packages"
    pkg_dir.mkdir()
    zip_path = pkg_dir / "bill-teaching-helper-1.0.0.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("manifest.json", b"{}")
    return pkg_dir


@pytest.fixture(scope="function")
def client(clean_db: None, fake_package_dir: Path) -> Generator[TestClient, None, None]:
    import main as main_module
    from main import app

    original_pkg_dir = main_module.EXTENSION_PACKAGES_DIR
    original_releases = main_module.extension_releases
    original_lock = main_module._extension_releases_lock

    main_module.EXTENSION_PACKAGES_DIR = fake_package_dir
    main_module.extension_releases = []
    main_module._extension_releases_lock = threading.Lock()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    main_module.EXTENSION_PACKAGES_DIR = original_pkg_dir
    main_module.extension_releases = original_releases
    main_module._extension_releases_lock = original_lock


def _make_user(client: TestClient, email: str, role: str, password: str = "Password1!") -> dict[str, Any]:
    from user_auth import create_user_account
    return create_user_account({
        "name": f"Test {role.capitalize()}",
        "email": email,
        "password": password,
        "role": role,
        "status": "active",
        "tenant_id": "default",
    })


def _login(client: TestClient, email: str, password: str = "Password1!") -> TestClient:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return client


def _admin_register_release(client: TestClient, filename: str = "bill-teaching-helper-1.0.0.zip") -> dict[str, Any]:
    resp = client.post(
        "/api/extension-releases",
        json={"version_label": "1.0.0", "file_name": filename, "release_notes": "Initial extension build"},
    )
    assert resp.status_code == 201, f"Register failed: {resp.text}"
    return resp.json()


def _extract_path_and_query(download_url: str) -> tuple[str, dict[str, list[str]]]:
    parsed = urlparse(download_url)
    return parsed.path, parse_qs(parsed.query)


class TestUnauthenticated:
    def test_current_requires_login(self, client: TestClient) -> None:
        resp = client.get("/api/extension-releases/current")
        assert resp.status_code == 401

    def test_list_requires_login(self, client: TestClient) -> None:
        resp = client.get("/api/extension-releases")
        assert resp.status_code == 401

    def test_download_requires_login(self, client: TestClient) -> None:
        resp = client.get("/api/extension-releases/fake-id/download")
        assert resp.status_code == 401

    def test_download_url_requires_login(self, client: TestClient) -> None:
        resp = client.post("/api/extension-releases/fake-id/download-url")
        assert resp.status_code == 401


class TestRolesAndCurrent:
    def test_viewer_cannot_get_current(self, client: TestClient) -> None:
        _make_user(client, "viewer@test.com", "viewer")
        _login(client, "viewer@test.com")
        resp = client.get("/api/extension-releases/current")
        assert resp.status_code == 403

    def test_teacher_gets_404_when_no_current(self, client: TestClient) -> None:
        _make_user(client, "teacher@test.com", "teacher")
        _login(client, "teacher@test.com")
        resp = client.get("/api/extension-releases/current")
        assert resp.status_code == 404

    def test_teacher_can_view_current(self, client: TestClient) -> None:
        _make_user(client, "admin_tc@test.com", "admin")
        _make_user(client, "teacher_current@test.com", "teacher")

        _login(client, "admin_tc@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "teacher_current@test.com")
        resp = client.get("/api/extension-releases/current")
        assert resp.status_code == 200
        data = resp.json()
        assert data["version_label"] == "1.0.0"
        assert data["status"] == "current"

    def test_runner_can_download_current(self, client: TestClient) -> None:
        _make_user(client, "admin_rd@test.com", "admin")
        _make_user(client, "runner_dl@test.com", "runner")

        _login(client, "admin_rd@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "runner_dl@test.com")
        resp = client.get(f"/api/extension-releases/{release['id']}/download")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/zip")

    def test_runner_can_get_download_url(self, client: TestClient) -> None:
        _make_user(client, "admin_edu@test.com", "admin")
        _make_user(client, "runner_edu@test.com", "runner")

        _login(client, "admin_edu@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "runner_edu@test.com")
        resp = client.post(f"/api/extension-releases/{release['id']}/download-url")
        assert resp.status_code == 200
        data = resp.json()
        assert data["release_id"] == release["id"]
        assert "/api/proxy" not in data["download_url"]
        assert "/api/extension-releases/" in data["download_url"]
        assert data["expires_in_seconds"] == 300


class TestAdminManagement:
    def test_admin_can_register_release(self, client: TestClient) -> None:
        _make_user(client, "admin_reg@test.com", "admin")
        _login(client, "admin_reg@test.com")
        release = _admin_register_release(client)
        assert release["version_label"] == "1.0.0"
        assert release["status"] == "draft"
        assert release["sha256_hash"] is not None
        assert len(release["sha256_hash"]) == 64

    def test_admin_sha256_is_correct(self, client: TestClient, fake_package_dir: Path) -> None:
        _make_user(client, "admin_sha@test.com", "admin")
        _login(client, "admin_sha@test.com")
        release = _admin_register_release(client)
        zip_path = fake_package_dir / "bill-teaching-helper-1.0.0.zip"
        expected = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        assert release["sha256_hash"] == expected

    def test_admin_can_mark_current(self, client: TestClient) -> None:
        _make_user(client, "admin_mark@test.com", "admin")
        _login(client, "admin_mark@test.com")
        release = _admin_register_release(client)
        resp = client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "current"

    def test_admin_can_disable_release(self, client: TestClient) -> None:
        _make_user(client, "admin_dis@test.com", "admin")
        _login(client, "admin_dis@test.com")
        release = _admin_register_release(client)
        resp = client.post(f"/api/extension-releases/{release['id']}/disable", json={"confirm": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    def test_non_admin_cannot_register(self, client: TestClient) -> None:
        _make_user(client, "teacher_reg@test.com", "teacher")
        _login(client, "teacher_reg@test.com")
        resp = client.post(
            "/api/extension-releases",
            json={"version_label": "1.0.0", "file_name": "bill-teaching-helper-1.0.0.zip"},
        )
        assert resp.status_code == 403

    def test_viewer_cannot_get_download_url(self, client: TestClient) -> None:
        _make_user(client, "admin_vdu@test.com", "admin")
        _make_user(client, "viewer_vdu@test.com", "viewer")

        _login(client, "admin_vdu@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "viewer_vdu@test.com")
        resp = client.post(f"/api/extension-releases/{release['id']}/download-url")
        assert resp.status_code == 403


class TestSecurityAndStatusRules:
    def test_path_traversal_filename_rejected(self, client: TestClient) -> None:
        _make_user(client, "admin_trav@test.com", "admin")
        _login(client, "admin_trav@test.com")
        resp = client.post(
            "/api/extension-releases",
            json={"version_label": "1.0.0", "file_name": "../../../etc/passwd"},
        )
        assert resp.status_code == 400

    def test_missing_file_returns_404(self, client: TestClient) -> None:
        _make_user(client, "admin_mis@test.com", "admin")
        _login(client, "admin_mis@test.com")
        resp = client.post(
            "/api/extension-releases",
            json={"version_label": "1.0.0", "file_name": "not-there.zip"},
        )
        assert resp.status_code == 404

    def test_teacher_cannot_download_disabled_release(self, client: TestClient) -> None:
        _make_user(client, "admin_d1@test.com", "admin")
        _make_user(client, "teacher_d1@test.com", "teacher")

        _login(client, "admin_d1@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})
        client.post(f"/api/extension-releases/{release['id']}/disable", json={"confirm": True})

        _login(client, "teacher_d1@test.com")
        resp = client.get(f"/api/extension-releases/{release['id']}/download")
        assert resp.status_code == 403

    def test_admin_can_download_disabled_release(self, client: TestClient) -> None:
        _make_user(client, "admin_d2@test.com", "admin")

        _login(client, "admin_d2@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/disable", json={"confirm": True})

        resp = client.get(f"/api/extension-releases/{release['id']}/download")
        assert resp.status_code == 200

    def test_mark_disabled_release_current_fails(self, client: TestClient) -> None:
        _make_user(client, "admin_d3@test.com", "admin")

        _login(client, "admin_d3@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/disable", json={"confirm": True})

        resp = client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})
        assert resp.status_code == 409

    def test_invalid_download_token_fails(self, client: TestClient) -> None:
        _make_user(client, "admin_badtoken@test.com", "admin")
        _login(client, "admin_badtoken@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        resp = client.get(f"/api/extension-releases/{release['id']}/download?token=invalid-token")
        assert resp.status_code == 403

    def test_expired_download_token_fails(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _make_user(client, "admin_exp@test.com", "admin")
        _make_user(client, "runner_exp@test.com", "runner")

        _login(client, "admin_exp@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "runner_exp@test.com")
        token_resp = client.post(f"/api/extension-releases/{release['id']}/download-url")
        assert token_resp.status_code == 200
        path, query = _extract_path_and_query(token_resp.json()["download_url"])
        token = query["token"][0]

        import main as main_module
        now = main_module.time.time()
        monkeypatch.setattr(main_module.time, "time", lambda: now + 301)

        resp = client.get(f"{path}?token={token}")
        assert resp.status_code == 403

    def test_tokenized_download_serves_file(self, client: TestClient) -> None:
        _make_user(client, "admin_tok@test.com", "admin")
        _make_user(client, "teacher_tok@test.com", "teacher")

        _login(client, "admin_tok@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "teacher_tok@test.com")
        token_resp = client.post(f"/api/extension-releases/{release['id']}/download-url")
        assert token_resp.status_code == 200
        path, query = _extract_path_and_query(token_resp.json()["download_url"])
        token = query["token"][0]

        resp = client.get(f"{path}?token={token}")
        assert resp.status_code == 200
        assert resp.headers.get("content-type", "").startswith("application/zip")

    def test_non_admin_token_cannot_download_after_release_disabled(self, client: TestClient) -> None:
        _make_user(client, "admin_tdis@test.com", "admin")
        _make_user(client, "runner_tdis@test.com", "runner")

        _login(client, "admin_tdis@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "runner_tdis@test.com")
        token_resp = client.post(f"/api/extension-releases/{release['id']}/download-url")
        assert token_resp.status_code == 200
        path, query = _extract_path_and_query(token_resp.json()["download_url"])
        token = query["token"][0]

        _login(client, "admin_tdis@test.com")
        disable_resp = client.post(f"/api/extension-releases/{release['id']}/disable", json={"confirm": True})
        assert disable_resp.status_code == 200

        client.cookies.clear()
        denied = client.get(f"{path}?token={token}")
        assert denied.status_code == 403


class TestAuditAndMetadata:
    def _get_audit_logs(self, client: TestClient) -> list[dict]:
        resp = client.get("/api/admin/audit-logs?limit=200")
        assert resp.status_code == 200
        return resp.json()

    def test_download_increments_count(self, client: TestClient) -> None:
        _make_user(client, "admin_dc@test.com", "admin")
        _make_user(client, "teacher_dc@test.com", "teacher")

        _login(client, "admin_dc@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "teacher_dc@test.com")
        client.get(f"/api/extension-releases/{release['id']}/download")

        _login(client, "admin_dc@test.com")
        all_releases = client.get("/api/extension-releases").json()
        row = next(r for r in all_releases if r["id"] == release["id"])
        assert row["download_count"] == 1

    def test_download_creates_audit_entry(self, client: TestClient) -> None:
        _make_user(client, "admin_aud@test.com", "admin")
        _make_user(client, "runner_aud@test.com", "runner")

        _login(client, "admin_aud@test.com")
        release = _admin_register_release(client)
        client.post(f"/api/extension-releases/{release['id']}/mark-current", json={"confirm": True})

        _login(client, "runner_aud@test.com")
        client.get(f"/api/extension-releases/{release['id']}/download")

        _login(client, "admin_aud@test.com")
        events = [e["event_type"] for e in self._get_audit_logs(client)]
        assert "extension_release_download_completed" in events
