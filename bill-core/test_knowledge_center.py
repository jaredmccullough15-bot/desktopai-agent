from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

from db import SessionLocal
from models_db import Tenant

os.environ.setdefault("BILL_CORE_AUTH_ENABLED", "false")


@pytest.fixture(autouse=True)
def clean_db() -> Generator[None, None, None]:
    import db

    db.Base.metadata.drop_all(bind=db.engine)
    db.Base.metadata.create_all(bind=db.engine)
    with SessionLocal() as session:
        session.query(Tenant).delete()
        session.add(Tenant(id="default", name="Internal", is_internal=True))
        session.commit()
    yield
    db.Base.metadata.drop_all(bind=db.engine)


@pytest.fixture(scope="function")
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    import main as main_module
    from main import app

    knowledge_path = tmp_path / "knowledge_center.json"
    monkeypatch.setattr(main_module, "KNOWLEDGE_CENTER_PATH", knowledge_path)
    main_module.knowledge_records = []
    main_module._releases_lock = threading.Lock()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _make_user(client: TestClient, email: str, role: str, password: str = "Password1!") -> dict[str, Any]:
    from user_auth import create_user_account

    return create_user_account(
        {
            "name": f"Test {role.capitalize()}",
            "email": email,
            "password": password,
            "role": role,
            "status": "active",
            "tenant_id": "default",
        }
    )


def _login(client: TestClient, email: str, password: str = "Password1!") -> None:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.text}"


def _create_knowledge(client: TestClient, *, title: str, category: str, content: str, tags: list[str], status: str = "draft") -> dict[str, Any]:
    resp = client.post(
        "/api/knowledge",
        json={
            "title": title,
            "category": category,
            "applies_to": ["crm"],
            "content": content,
            "source_type": "manual",
            "tags": tags,
            "status": status,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestKnowledgePermissions:
    def test_admin_can_create_knowledge(self, client: TestClient) -> None:
        _make_user(client, "admin_knowledge@test.com", "admin")
        _login(client, "admin_knowledge@test.com")

        record = _create_knowledge(
            client,
            title="CRM Standard A",
            category="crm_policy",
            content="Use consistent client naming.",
            tags=["crm", "keap"],
            status="draft",
        )
        assert record["knowledge_id"]
        assert record["title"] == "CRM Standard A"

    def test_non_admin_cannot_create_knowledge(self, client: TestClient) -> None:
        _make_user(client, "teacher_knowledge@test.com", "teacher")
        _login(client, "teacher_knowledge@test.com")

        resp = client.post(
            "/api/knowledge",
            json={
                "title": "Should Fail",
                "category": "crm_policy",
                "applies_to": ["crm"],
                "content": "Teachers cannot create admin knowledge.",
                "source_type": "manual",
                "tags": ["crm"],
                "status": "active",
            },
        )
        assert resp.status_code == 403


class TestKnowledgeLifecycle:
    def test_active_knowledge_can_be_retrieved(self, client: TestClient) -> None:
        _make_user(client, "admin_active@test.com", "admin")
        _make_user(client, "runner_active@test.com", "runner")

        _login(client, "admin_active@test.com")
        _create_knowledge(
            client,
            title="Active CRM Guide",
            category="crm_policy",
            content="Always validate client record completeness.",
            tags=["crm", "policy"],
            status="active",
        )

        _login(client, "runner_active@test.com")
        resp = client.get("/api/knowledge/active")
        assert resp.status_code == 200
        payload = resp.json()
        assert len(payload) >= 1
        assert payload[0]["status"] == "active"

    def test_archived_knowledge_not_returned_by_default(self, client: TestClient) -> None:
        _make_user(client, "admin_arch@test.com", "admin")
        _make_user(client, "teacher_arch@test.com", "teacher")

        _login(client, "admin_arch@test.com")
        created = _create_knowledge(
            client,
            title="Archive Me",
            category="crm_policy",
            content="Temporary reference",
            tags=["crm"],
            status="active",
        )
        archive_resp = client.post(f"/api/knowledge/{created['knowledge_id']}/archive")
        assert archive_resp.status_code == 200
        assert archive_resp.json()["status"] == "archived"

        _login(client, "teacher_arch@test.com")
        active_resp = client.get("/api/knowledge/active")
        assert active_resp.status_code == 200
        assert all(item["knowledge_id"] != created["knowledge_id"] for item in active_resp.json())

    def test_audit_log_records_knowledge_changes(self, client: TestClient) -> None:
        _make_user(client, "admin_audit@test.com", "admin")
        _login(client, "admin_audit@test.com")

        created = _create_knowledge(
            client,
            title="Audit Standard",
            category="crm_policy",
            content="Record all key updates.",
            tags=["crm", "audit"],
            status="draft",
        )
        knowledge_id = created["knowledge_id"]

        update_resp = client.patch(
            f"/api/knowledge/{knowledge_id}",
            json={"status": "active", "content": "Record all key updates and reasons."},
        )
        assert update_resp.status_code == 200

        archive_resp = client.post(f"/api/knowledge/{knowledge_id}/archive")
        assert archive_resp.status_code == 200

        audit_resp = client.get("/api/admin/audit-logs?limit=200")
        assert audit_resp.status_code == 200
        events = [str(item.get("event_type") or "") for item in audit_resp.json()]
        assert "knowledge_created" in events
        assert "knowledge_updated" in events
        assert "knowledge_archived" in events


class TestKnowledgeRelevanceAndBehavior:
    def test_keap_tagged_knowledge_retrieved_for_keap_context(self, client: TestClient) -> None:
        _make_user(client, "admin_keap@test.com", "admin")
        _make_user(client, "runner_keap@test.com", "runner")

        _login(client, "admin_keap@test.com")
        _create_knowledge(
            client,
            title="Keap Client Record Standard",
            category="crm_standard",
            content="For Keap client records, include full household and policy metadata.",
            tags=["keap", "crm", "client record"],
            status="active",
        )

        _login(client, "runner_keap@test.com")
        resp = client.get("/api/knowledge/active", params={"context": "Need Keap CRM client record follow-up standards"})
        assert resp.status_code == 200
        data = resp.json()
        assert data
        assert any("keap" in " ".join(item.get("tags") or []).lower() for item in data)

    def test_knowledge_does_not_create_executable_workflow_steps(self, client: TestClient) -> None:
        _make_user(client, "admin_nonexec@test.com", "admin")
        _login(client, "admin_nonexec@test.com")
        _create_knowledge(
            client,
            title="Policy Notes Only",
            category="crm_policy",
            content="Policies guide reasoning but do not define click steps.",
            tags=["policy", "crm"],
            status="active",
        )

        import main as main_module

        draft = {
            "workflow_name": "policy_only_workflow",
            "goal": "Apply policy understanding",
            "steps": [],
        }
        readiness = main_module.validate_taught_workflow_executable(draft)
        assert readiness["runnable"] is False
        assert int(readiness.get("executable_action_count") or 0) == 0
