from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from db import SessionLocal
from models_db import IntegrationCredential, Tenant

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

    monkeypatch.setattr(main_module, "KNOWLEDGE_CENTER_PATH", tmp_path / "knowledge_center.json")
    monkeypatch.setattr(main_module, "TENANT_PROFILES_PATH", tmp_path / "tenant_profiles.json")
    monkeypatch.setattr(main_module, "INTEGRATION_SECRET_KEY_PATH", tmp_path / "integration_secret.key")
    main_module._integration_fernet_instance = None
    main_module.knowledge_records = []
    main_module._releases_lock = threading.Lock()

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _make_user(email: str, role: str, tenant_id: str = "default", password: str = "Password1!") -> dict[str, Any]:
    from user_auth import create_user_account

    return create_user_account(
        {
            "name": f"Test {role}",
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


def _create_tenant(client: TestClient, tenant_id: str) -> None:
    response = client.post(
        "/api/super-admin/tenants",
        json={"tenant_id": tenant_id, "name": tenant_id},
    )
    assert response.status_code == 201, response.text


def _workflow_template_payload(workflow_id: str, workflow_name: str) -> dict[str, Any]:
    return {
        "tenant_id": "ignored-by-endpoint",
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "systems": [],
        "actions": [
            {
                "action_key": "noop.action",
                "action_type": "noop",
                "description": "No-op action",
                "steps": [],
            }
        ],
        "identity_policy": {
            "fields": [],
            "auto_proceed_score": 70,
            "human_review_score": 40,
            "block_below_score": 40,
        },
        "decision_rules": [
            {
                "rule_id": "rule-1",
                "description": "Always noop",
                "priority": 1,
                "conditions": [{"field": "audit.status", "operator": "eq", "value": "any"}],
                "action_key": "noop.action",
            }
        ],
    }


def test_super_admin_routes_require_super_admin_role(client: TestClient) -> None:
    _make_user("tenant-admin@test.com", "admin")
    _login(client, "tenant-admin@test.com")

    forbidden = client.get("/api/super-admin/tenants")
    assert forbidden.status_code == 403


def test_super_admin_tenant_create_update_and_audit(client: TestClient) -> None:
    _make_user("platform@test.com", "super_admin")
    _login(client, "platform@test.com")

    created = client.post(
        "/api/super-admin/tenants",
        json={
            "tenant_id": "acme-west",
            "name": "Acme West",
            "contact_email": "ops@acme.test",
            "notes": "Initial onboarding",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["tenant_id"] == "acme-west"

    updated = client.patch(
        "/api/super-admin/tenants/acme-west",
        json={"status": "suspended", "notes": "Billing hold"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "suspended"
    assert updated.json()["notes"] == "Billing hold"

    listed = client.get("/api/super-admin/tenants")
    assert listed.status_code == 200, listed.text
    tenants = {item["tenant_id"]: item for item in listed.json()}
    assert "acme-west" in tenants

    audit = client.get("/api/admin/audit-logs", params={"limit": 300})
    assert audit.status_code == 200, audit.text
    event_types = [row["event_type"] for row in audit.json()]
    assert "super_admin_tenant_created" in event_types
    assert "super_admin_tenant_updated" in event_types


def test_integration_secret_lifecycle_encrypted_masked_and_audited(client: TestClient) -> None:
    _make_user("platform2@test.com", "super_admin")
    _login(client, "platform2@test.com")

    _create_tenant(client, "beta-tenant")

    secret_value = "abcd1234TOKEN"
    created = client.post(
        "/api/super-admin/tenants/beta-tenant/integration-credentials",
        json={
            "integration_type": "crm",
            "name": "Keap Primary",
            "secret": secret_value,
            "status": "active",
            "settings": {"base_url": "https://example.test"},
        },
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["tenant_id"] == "beta-tenant"
    assert payload["secret_masked"] != secret_value
    assert "secret" not in payload

    list_resp = client.get("/api/super-admin/tenants/beta-tenant/integration-credentials")
    assert list_resp.status_code == 200, list_resp.text
    assert len(list_resp.json()) == 1

    integration_id = payload["integration_id"]

    with SessionLocal() as session:
        row = session.query(IntegrationCredential).filter_by(tenant_id="beta-tenant").first()
        assert row is not None
        encrypted_before = row.secret_encrypted
        assert row.secret_encrypted != secret_value
        assert row.secret_masked == payload["secret_masked"]

    updated = client.patch(
        f"/api/super-admin/tenants/beta-tenant/integration-credentials/{integration_id}",
        json={"secret": "NEWSECRETVALUE9988", "settings": {"base_url": "https://new.example.test"}},
    )
    assert updated.status_code == 200, updated.text
    assert "secret" not in updated.json()

    with SessionLocal() as session:
        row_after = session.get(IntegrationCredential, integration_id)
        assert row_after is not None
        assert row_after.secret_encrypted != encrypted_before

    archived = client.delete(f"/api/super-admin/tenants/beta-tenant/integration-credentials/{integration_id}")
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"

    audit = client.get("/api/admin/audit-logs", params={"limit": 400})
    assert audit.status_code == 200, audit.text
    records = audit.json()
    event_types = [item["event_type"] for item in records]
    assert "super_admin_integration_credential_created" in event_types
    assert "super_admin_integration_credential_updated" in event_types
    assert "super_admin_integration_credential_deleted" in event_types

    joined_details = "\n".join(str(item.get("details") or "") for item in records)
    joined_redacted = "\n".join(str(item.get("redacted_payload") or "") for item in records)
    assert "abcd1234TOKEN" not in joined_details
    assert "abcd1234TOKEN" not in joined_redacted
    assert "NEWSECRETVALUE9988" not in joined_details
    assert "NEWSECRETVALUE9988" not in joined_redacted


def test_super_admin_can_copy_knowledge_between_tenants_with_attribution(client: TestClient) -> None:
    _make_user("platform3@test.com", "super_admin")
    _login(client, "platform3@test.com")

    for tenant_id in ("source-tenant", "target-tenant"):
        _create_tenant(client, tenant_id)

    create_knowledge = client.post(
        "/api/knowledge",
        json={
            "title": "Cross Tenant Standard",
            "category": "crm_policy",
            "applies_to": ["crm"],
            "content": "Always confirm policy dates before updates.",
            "source_type": "manual",
            "tags": ["crm", "policy"],
            "status": "active",
            "tenant_id": "source-tenant",
        },
    )
    assert create_knowledge.status_code == 201, create_knowledge.text
    source_id = create_knowledge.json()["knowledge_id"]

    copied = client.post(
        "/api/super-admin/knowledge/copy",
        json={
            "source_tenant_id": "source-tenant",
            "source_knowledge_id": source_id,
            "target_tenant_id": "target-tenant",
            "activate": True,
        },
    )
    assert copied.status_code == 200, copied.text
    copied_payload = copied.json()
    assert copied_payload["tenant_id"] == "target-tenant"
    assert copied_payload["status"] == "active"
    assert copied_payload["copied_from_tenant_id"] == "source-tenant"
    assert copied_payload["copied_from_record_id"] == source_id
    assert copied_payload["copied_by_user_id"]
    assert copied_payload["copied_at"]

    target_knowledge = client.get("/api/super-admin/tenants/target-tenant/knowledge")
    assert target_knowledge.status_code == 200, target_knowledge.text
    assert any(item["knowledge_id"] == copied_payload["knowledge_id"] for item in target_knowledge.json())

    source_knowledge = client.get("/api/super-admin/tenants/source-tenant/knowledge")
    assert source_knowledge.status_code == 200, source_knowledge.text
    assert any(item["knowledge_id"] == source_id for item in source_knowledge.json())


def test_super_admin_can_copy_workflow_and_apply_bundle(client: TestClient) -> None:
    _make_user("platform4@test.com", "super_admin")
    _make_user("source-admin@test.com", "admin", tenant_id="source-tenant")
    _login(client, "platform4@test.com")
    _create_tenant(client, "source-tenant")
    _create_tenant(client, "target-tenant")

    _login(client, "source-admin@test.com")
    create_template = client.post(
        "/api/tenant-templates/source-tenant/workflows",
        json=_workflow_template_payload("renewal-audit", "Renewal Audit"),
    )
    assert create_template.status_code == 201, create_template.text

    _login(client, "platform4@test.com")
    copied = client.post(
        "/api/super-admin/workflows/copy",
        json={
            "source_tenant_id": "source-tenant",
            "source_workflow_id": "renewal-audit",
            "target_tenant_id": "target-tenant",
            "activate": False,
        },
    )
    assert copied.status_code == 200, copied.text
    copied_payload = copied.json()
    assert copied_payload["tenant_id"] == "target-tenant"
    assert copied_payload["enabled"] is False
    assert copied_payload["workflow_id"] != "renewal-audit"

    bundle_id = f"starter-bundle-{uuid4().hex[:8]}"
    bundle_create = client.post(
        "/api/super-admin/template-bundles",
        json={
            "bundle_id": bundle_id,
            "name": "Starter Bundle",
            "templates": [
                {
                    "source_tenant_id": "source-tenant",
                    "workflow_id": "renewal-audit",
                    "activate": False,
                }
            ],
        },
    )
    assert bundle_create.status_code == 201, bundle_create.text

    applied = client.post(f"/api/super-admin/tenants/target-tenant/template-bundles/{bundle_id}/apply")
    assert applied.status_code == 200, applied.text
    assert applied.json()["copied_count"] >= 1


def test_cross_tenant_denial_paths_for_admin_and_viewer(client: TestClient) -> None:
    _make_user("platform5@test.com", "super_admin")
    _login(client, "platform5@test.com")
    _create_tenant(client, "tenant-a")
    _create_tenant(client, "tenant-b")

    _make_user("a-admin@test.com", "admin", tenant_id="tenant-a")
    _make_user("a-viewer@test.com", "viewer", tenant_id="tenant-a")
    _make_user("b-user@test.com", "runner", tenant_id="tenant-b")

    _login(client, "a-admin@test.com")

    list_tenants = client.get("/api/tenants")
    assert list_tenants.status_code == 200, list_tenants.text
    assert len(list_tenants.json()) <= 1
    assert all(item["tenant_id"] == "tenant-a" for item in list_tenants.json())

    other_users = client.get("/api/admin/users", params={"tenant_id": "tenant-b"})
    assert other_users.status_code == 200, other_users.text
    assert all(item["tenant_id"] == "tenant-a" for item in other_users.json())

    other_knowledge = client.get("/api/knowledge", params={"tenant_id": "tenant-b"})
    assert other_knowledge.status_code == 200, other_knowledge.text
    assert all(item["tenant_id"] in (None, "tenant-a") for item in other_knowledge.json())

    other_workflows = client.get("/api/tenant-templates/tenant-b")
    assert other_workflows.status_code == 403

    forbidden_copy_knowledge = client.post(
        "/api/super-admin/knowledge/copy",
        json={
            "source_tenant_id": "tenant-b",
            "source_knowledge_id": "missing",
            "target_tenant_id": "tenant-a",
            "activate": False,
        },
    )
    assert forbidden_copy_knowledge.status_code == 403

    forbidden_copy_workflow = client.post(
        "/api/super-admin/workflows/copy",
        json={
            "source_tenant_id": "tenant-b",
            "source_workflow_id": "wf-b",
            "target_tenant_id": "tenant-a",
            "activate": False,
        },
    )
    assert forbidden_copy_workflow.status_code == 403

    forbidden_other_integration = client.get("/api/admin/tenants/tenant-b/integration-credentials")
    assert forbidden_other_integration.status_code == 403

    _login(client, "a-viewer@test.com")
    viewer_forbidden_admin_users = client.get("/api/admin/users")
    assert viewer_forbidden_admin_users.status_code == 403
    viewer_forbidden_integration = client.get("/api/admin/tenants/tenant-a/integration-credentials")
    assert viewer_forbidden_integration.status_code == 403


def test_super_admin_must_use_explicit_super_admin_routes(client: TestClient) -> None:
    _make_user("platform6@test.com", "super_admin")
    _login(client, "platform6@test.com")
    _create_tenant(client, "tenant-z")

    legacy_tenant_route = client.get("/api/tenants/tenant-z")
    assert legacy_tenant_route.status_code == 403

    legacy_template_route = client.get("/api/tenant-templates")
    assert legacy_template_route.status_code == 403

    explicit_route = client.get("/api/super-admin/tenants")
    assert explicit_route.status_code == 200


def test_blank_tenant_starts_empty(client: TestClient) -> None:
    _make_user("platform7@test.com", "super_admin")
    _login(client, "platform7@test.com")
    _create_tenant(client, "blank-tenant")

    users_resp = client.get("/api/super-admin/tenants/blank-tenant/users")
    knowledge_resp = client.get("/api/super-admin/tenants/blank-tenant/knowledge")
    workflows_resp = client.get("/api/super-admin/tenants/blank-tenant/workflows")
    integrations_resp = client.get("/api/super-admin/tenants/blank-tenant/integration-credentials")
    workers_resp = client.get("/api/super-admin/tenants/blank-tenant/workers")
    tenants_resp = client.get("/api/super-admin/tenants")

    assert users_resp.status_code == 200 and users_resp.json() == []
    assert knowledge_resp.status_code == 200 and knowledge_resp.json() == []
    assert workflows_resp.status_code == 200 and workflows_resp.json()["workflows"] == []
    assert integrations_resp.status_code == 200 and integrations_resp.json() == []
    assert workers_resp.status_code == 200 and workers_resp.json()["workers"] == []

    tenant_row = next(item for item in tenants_resp.json() if item["tenant_id"] == "blank-tenant")
    assert tenant_row["settings"] == {}
