from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from tenant_schemas import TenantCreateRequest, TenantRecord, TenantUpdateRequest

_DEFAULT_TENANTS_PATH = Path(__file__).resolve().parent / "tenants_store.json"
TENANTS_STORE_PATH = Path(os.getenv("BILL_CORE_TENANTS_STORE") or str(_DEFAULT_TENANTS_PATH))


def _safe_id(value: str) -> str:
    return "".join(c for c in str(value) if c.isalnum() or c in ("-", "_")).strip("-_")


def _load_tenants() -> dict[str, dict]:
    if not TENANTS_STORE_PATH.exists():
        return {}
    try:
        raw = json.loads(TENANTS_STORE_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for tenant_id, tenant in raw.items():
        if isinstance(tenant, dict):
            out[str(tenant_id)] = tenant
    return out


def _save_tenants(store: dict[str, dict]) -> None:
    TENANTS_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TENANTS_STORE_PATH.write_text(json.dumps(store, indent=2), encoding="utf-8")


def list_tenants() -> list[TenantRecord]:
    store = _load_tenants()
    records: list[TenantRecord] = []
    for tenant in store.values():
        try:
            records.append(TenantRecord.model_validate(tenant))
        except Exception:
            continue
    records.sort(key=lambda item: item.tenant_id)
    return records


def get_tenant(tenant_id: str) -> TenantRecord | None:
    safe_id = _safe_id(tenant_id)
    if not safe_id:
        return None
    tenant = _load_tenants().get(safe_id)
    if not isinstance(tenant, dict):
        return None
    try:
        return TenantRecord.model_validate(tenant)
    except Exception:
        return None


def create_tenant(payload: TenantCreateRequest) -> TenantRecord:
    safe_id = _safe_id(payload.tenant_id)
    if not safe_id:
        raise ValueError("Invalid tenant_id")

    store = _load_tenants()
    if safe_id in store:
        raise ValueError(f"Tenant already exists: {safe_id}")

    now = datetime.utcnow().isoformat() + "Z"
    record = TenantRecord(
        tenant_id=safe_id,
        name=str(payload.name).strip() or safe_id,
        workflows=[str(w).strip() for w in (payload.workflows or []) if str(w).strip()],
        systems=[str(s).strip() for s in (payload.systems or []) if str(s).strip()],
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    store[safe_id] = record.model_dump()
    _save_tenants(store)
    return record


def update_tenant(tenant_id: str, payload: TenantUpdateRequest) -> TenantRecord:
    safe_id = _safe_id(tenant_id)
    if not safe_id:
        raise ValueError("Invalid tenant_id")

    store = _load_tenants()
    current = store.get(safe_id)
    if not isinstance(current, dict):
        raise FileNotFoundError(f"Tenant not found: {safe_id}")

    record = TenantRecord.model_validate(current)
    if payload.name is not None:
        record.name = str(payload.name).strip() or record.name
    if payload.workflows is not None:
        record.workflows = [str(w).strip() for w in payload.workflows if str(w).strip()]
    if payload.systems is not None:
        record.systems = [str(s).strip() for s in payload.systems if str(s).strip()]
    if payload.status is not None:
        record.status = payload.status
    record.updated_at = datetime.utcnow().isoformat() + "Z"

    store[safe_id] = record.model_dump()
    _save_tenants(store)
    return record


def ensure_tenant_workflow_link(tenant_id: str, workflow_id: str, systems: list[str] | None = None) -> TenantRecord:
    safe_tenant = _safe_id(tenant_id)
    safe_workflow = _safe_id(workflow_id)
    if not safe_tenant or not safe_workflow:
        raise ValueError("Invalid tenant_id/workflow_id")

    store = _load_tenants()
    current = store.get(safe_tenant)
    now = datetime.utcnow().isoformat() + "Z"

    if isinstance(current, dict):
        record = TenantRecord.model_validate(current)
    else:
        record = TenantRecord(
            tenant_id=safe_tenant,
            name=safe_tenant,
            workflows=[],
            systems=[],
            status="active",
            created_at=now,
            updated_at=now,
        )

    if safe_workflow not in record.workflows:
        record.workflows.append(safe_workflow)

    if systems:
        existing = set(record.systems)
        for system in systems:
            s = str(system).strip()
            if s and s not in existing:
                record.systems.append(s)
                existing.add(s)

    record.updated_at = now
    store[safe_tenant] = record.model_dump()
    _save_tenants(store)
    return record
