"""
db_writes.py — Mirror-write helpers for Bill Core Phase 1.

These functions accept the same dict objects that main.py already builds,
map them into ORM models, and upsert them into the database.

They are designed to be called AFTER the existing JSON write so that any
failure here never breaks the existing API response.

All writes use the default tenant ("default") until Phase 2 introduces
real auth and per-tenant routing.
"""
import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from db import SessionLocal
from models_db import (
    AuditLogEntry,
    ImprovementProposal,
    Interaction,
    OperationalMemory,
    Preference,
    SOPSummary,
    Task,
    TaskReflection,
    UserAccount,
    UserSession,
    Worker,
    WorkerRelease,
    WorkflowDraft,
    WorkflowRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(obj: Any) -> str:
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return "{}"


def _now() -> datetime:
    return datetime.utcnow()


def _safe_write(label: str, fn):
    """Wrap a DB write so it never raises into the caller."""
    try:
        fn()
    except Exception as exc:
        logger.warning("DB mirror write failed [%s]: %s", label, exc)


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

def save_worker_db(worker: dict) -> None:
    """Upsert a worker dict into the workers table."""
    def _write():
        uuid = str(worker.get("machine_uuid") or "")
        if not uuid:
            return
        tenant_id = str(worker.get("tenant_id") or DEFAULT_TENANT_ID)
        with SessionLocal() as session:
            existing = session.query(Worker).filter_by(machine_uuid=uuid).first()
            now = _now()
            if existing:
                existing.tenant_id = tenant_id
                existing.machine_name = worker.get("machine_name")
                existing.status = worker.get("status")
                existing.worker_version = worker.get("worker_version")
                existing.execution_mode = worker.get("execution_mode")
                existing.current_task_id = worker.get("current_task_id")
                existing.last_seen = worker.get("last_seen")
                existing.token = worker.get("token")
                existing.data = _json(worker)
                existing.updated_at = now
            else:
                session.add(Worker(
                    tenant_id=tenant_id,
                    machine_uuid=uuid,
                    machine_name=worker.get("machine_name"),
                    status=worker.get("status"),
                    worker_version=worker.get("worker_version"),
                    execution_mode=worker.get("execution_mode"),
                    current_task_id=worker.get("current_task_id"),
                    last_seen=worker.get("last_seen"),
                    token=worker.get("token"),
                    data=_json(worker),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_worker_db", _write)


def delete_worker_db(machine_uuid: str) -> None:
    def _write():
        with SessionLocal() as session:
            session.query(Worker).filter_by(machine_uuid=machine_uuid).delete()
            session.commit()
    _safe_write("delete_worker_db", _write)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def save_task_db(task: dict) -> None:
    """Upsert a task dict into the tasks table."""
    def _write():
        task_id = str(task.get("id") or "")
        if not task_id:
            return
        payload = task.get("payload") or {}
        tenant_id = str(task.get("tenant_id") or payload.get("tenant_id") or DEFAULT_TENANT_ID)
        with SessionLocal() as session:
            existing = session.get(Task, task_id)
            now = _now()
            if existing:
                existing.tenant_id = tenant_id
                existing.status = task.get("status")
                existing.task_type = payload.get("task_type")
                existing.assigned_machine_uuid = task.get("assigned_machine_uuid")
                existing.result_json = _json(task.get("result_json"))
                existing.error = task.get("error")
                existing.completed_at = task.get("completed_at")
                existing.data = _json(task)
                existing.updated_at = now
            else:
                session.add(Task(
                    id=task_id,
                    tenant_id=tenant_id,
                    status=task.get("status"),
                    task_type=payload.get("task_type"),
                    assigned_machine_uuid=task.get("assigned_machine_uuid"),
                    result_json=_json(task.get("result_json")),
                    error=task.get("error"),
                    completed_at=task.get("completed_at"),
                    data=_json(task),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_task_db", _write)


# ---------------------------------------------------------------------------
# Worker Releases
# ---------------------------------------------------------------------------

def save_release_db(release: dict) -> None:
    """Upsert a release dict into the worker_releases table."""
    def _write():
        release_id = str(release.get("id") or "")
        if not release_id:
            return
        with SessionLocal() as session:
            existing = session.get(WorkerRelease, release_id)
            now = _now()
            if existing:
                existing.version = release.get("version")
                existing.channel = release.get("channel")
                existing.is_active = bool(release.get("is_active", False))
                existing.package_filename = release.get("package_filename")
                existing.package_sha256 = release.get("package_sha256")
                existing.release_notes = release.get("release_notes")
                existing.upload_time = release.get("upload_time")
                existing.data = _json(release)
                existing.updated_at = now
            else:
                session.add(WorkerRelease(
                    id=release_id,
                    tenant_id=DEFAULT_TENANT_ID,
                    version=release.get("version"),
                    channel=release.get("channel"),
                    is_active=bool(release.get("is_active", False)),
                    package_filename=release.get("package_filename"),
                    package_sha256=release.get("package_sha256"),
                    release_notes=release.get("release_notes"),
                    upload_time=release.get("upload_time"),
                    data=_json(release),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_release_db", _write)


def delete_release_db(release_id: str) -> None:
    def _write():
        with SessionLocal() as session:
            session.query(WorkerRelease).filter_by(id=release_id).delete()
            session.commit()
    _safe_write("delete_release_db", _write)


def save_all_releases_db(releases: list[dict]) -> None:
    """Sync the full releases list to DB (used after bulk status changes)."""
    for r in releases:
        save_release_db(r)


# ---------------------------------------------------------------------------
# Task Reflections
# ---------------------------------------------------------------------------

def save_reflection_db(reflection: dict) -> None:
    def _write():
        ref_id = str(reflection.get("id") or "")
        if not ref_id:
            return
        with SessionLocal() as session:
            existing = session.get(TaskReflection, ref_id)
            now = _now()
            if existing:
                existing.task_id = reflection.get("task_id")
                existing.workflow_name = reflection.get("workflow_name")
                existing.worker_name = reflection.get("worker_name")
                existing.status = reflection.get("status")
                existing.failure_classification = reflection.get("failure_classification")
                existing.timestamp = reflection.get("timestamp")
                existing.data = _json(reflection)
                existing.updated_at = now
            else:
                session.add(TaskReflection(
                    id=ref_id,
                    tenant_id=DEFAULT_TENANT_ID,
                    task_id=reflection.get("task_id"),
                    workflow_name=reflection.get("workflow_name"),
                    worker_name=reflection.get("worker_name"),
                    status=reflection.get("status"),
                    failure_classification=reflection.get("failure_classification"),
                    timestamp=reflection.get("timestamp"),
                    data=_json(reflection),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_reflection_db", _write)


# ---------------------------------------------------------------------------
# Improvement Proposals
# ---------------------------------------------------------------------------

def save_proposal_db(proposal: dict) -> None:
    def _write():
        prop_id = str(proposal.get("proposal_id") or "")
        if not prop_id:
            return
        with SessionLocal() as session:
            existing = session.get(ImprovementProposal, prop_id)
            now = _now()
            if existing:
                existing.workflow_name = proposal.get("workflow_name")
                existing.proposal_type = proposal.get("proposal_type")
                existing.status = proposal.get("status")
                existing.confidence = str(proposal.get("confidence", ""))
                existing.created_at_iso = proposal.get("created_at")
                existing.data = _json(proposal)
                existing.updated_at = now
            else:
                session.add(ImprovementProposal(
                    id=prop_id,
                    tenant_id=DEFAULT_TENANT_ID,
                    workflow_name=proposal.get("workflow_name"),
                    proposal_type=proposal.get("proposal_type"),
                    status=proposal.get("status"),
                    confidence=str(proposal.get("confidence", "")),
                    created_at_iso=proposal.get("created_at"),
                    data=_json(proposal),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_proposal_db", _write)


# ---------------------------------------------------------------------------
# Operational Memory
# ---------------------------------------------------------------------------

def save_memory_db(mem: dict) -> None:
    def _write():
        mem_id = str(mem.get("id") or "")
        if not mem_id:
            return
        with SessionLocal() as session:
            existing = session.get(OperationalMemory, mem_id)
            now = _now()
            if existing:
                existing.kind = mem.get("kind")
                existing.summary = mem.get("summary")
                existing.timestamp = mem.get("timestamp")
                existing.data = _json(mem)
                existing.updated_at = now
            else:
                session.add(OperationalMemory(
                    id=mem_id,
                    tenant_id=DEFAULT_TENANT_ID,
                    kind=mem.get("kind"),
                    summary=mem.get("summary"),
                    timestamp=mem.get("timestamp"),
                    data=_json(mem),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_memory_db", _write)


# ---------------------------------------------------------------------------
# Users / Sessions / Audit Log
# ---------------------------------------------------------------------------

def save_user_db(user: dict) -> None:
    def _write():
        user_id = str(user.get("id") or "") or str(uuid4())
        email = str(user.get("email") or "").strip().lower()
        if not email:
            return
        with SessionLocal() as session:
            existing = (
                session.query(UserAccount)
                .filter_by(tenant_id=str(user.get("tenant_id") or DEFAULT_TENANT_ID), email=email)
                .first()
            )
            now = _now()
            payload = _json(user)
            if existing:
                existing.name = str(user.get("name") or existing.name)
                existing.role = str(user.get("role") or existing.role)
                existing.status = str(user.get("status") or existing.status)
                if user.get("password_hash"):
                    existing.password_hash = str(user.get("password_hash"))
                if user.get("password_salt"):
                    existing.password_salt = str(user.get("password_salt"))
                existing.last_login_at = user.get("last_login_at") or existing.last_login_at
                existing.data = payload
                existing.updated_at = now
            else:
                session.add(UserAccount(
                    id=user_id,
                    tenant_id=str(user.get("tenant_id") or DEFAULT_TENANT_ID),
                    email=email,
                    name=str(user.get("name") or email),
                    role=str(user.get("role") or "viewer"),
                    status=str(user.get("status") or "active"),
                    password_hash=str(user.get("password_hash") or ""),
                    password_salt=str(user.get("password_salt") or ""),
                    last_login_at=user.get("last_login_at"),
                    data=payload,
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_user_db", _write)


def save_user_session_db(session_data: dict) -> None:
    def _write():
        session_id = str(session_data.get("id") or session_data.get("session_id") or uuid4())
        token_hash = str(session_data.get("session_token_hash") or "")
        user_id = str(session_data.get("user_id") or "")
        if not token_hash or not user_id:
            return
        with SessionLocal() as session:
            existing = session.get(UserSession, session_id)
            now = _now()
            if existing:
                existing.user_id = user_id
                existing.session_token_hash = token_hash
                existing.expires_at = session_data.get("expires_at") or existing.expires_at
                existing.revoked_at = session_data.get("revoked_at") or existing.revoked_at
                existing.last_seen_at = session_data.get("last_seen_at") or existing.last_seen_at
                existing.created_ip = session_data.get("created_ip") or existing.created_ip
                existing.user_agent = session_data.get("user_agent") or existing.user_agent
                existing.data = _json(session_data)
                existing.updated_at = now
            else:
                session.add(UserSession(
                    id=session_id,
                    tenant_id=str(session_data.get("tenant_id") or DEFAULT_TENANT_ID),
                    user_id=user_id,
                    session_token_hash=token_hash,
                    expires_at=session_data.get("expires_at") or now,
                    revoked_at=session_data.get("revoked_at"),
                    last_seen_at=session_data.get("last_seen_at"),
                    created_ip=session_data.get("created_ip"),
                    user_agent=session_data.get("user_agent"),
                    data=_json(session_data),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_user_session_db", _write)


def save_audit_log_db(entry: dict) -> None:
    def _write():
        tenant_id = str(entry.get("tenant_id") or DEFAULT_TENANT_ID)
        event_type = str(entry.get("event_type") or "")
        if not event_type:
            return
        with SessionLocal() as session:
            session.add(AuditLogEntry(
                tenant_id=tenant_id,
                event_type=event_type,
                actor_user_id=entry.get("actor_user_id"),
                actor_user_name=entry.get("actor_user_name"),
                actor_role=entry.get("actor_role"),
                target_type=entry.get("target_type"),
                target_id=entry.get("target_id"),
                request_method=entry.get("request_method"),
                request_path=entry.get("request_path"),
                status_code=entry.get("status_code"),
                details_json=_json(entry.get("details") or {}),
                redacted_payload=_json(entry.get("redacted_payload") or {}),
                source=entry.get("source"),
                created_at=_now(),
                updated_at=_now(),
            ))
            session.commit()
    _safe_write("save_audit_log_db", _write)


# ---------------------------------------------------------------------------
# Interactions (interactive prompts)
# ---------------------------------------------------------------------------

def save_interaction_db(prompt: dict) -> None:
    def _write():
        iid = str(prompt.get("interaction_id") or "")
        if not iid:
            return
        with SessionLocal() as session:
            existing = session.get(Interaction, iid)
            now = _now()
            if existing:
                existing.interaction_type = prompt.get("interaction_type")
                existing.status = prompt.get("status")
                existing.command = prompt.get("command")
                existing.workflow_name = prompt.get("workflow_name")
                existing.created_at_iso = prompt.get("created_at")
                existing.data = _json(prompt)
                existing.updated_at = now
            else:
                session.add(Interaction(
                    id=iid,
                    tenant_id=DEFAULT_TENANT_ID,
                    interaction_type=prompt.get("interaction_type"),
                    status=prompt.get("status"),
                    command=prompt.get("command"),
                    workflow_name=prompt.get("workflow_name"),
                    created_at_iso=prompt.get("created_at"),
                    data=_json(prompt),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_interaction_db", _write)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------

def save_preference_db(pref: dict) -> None:
    def _write():
        key = str(pref.get("key") or "")
        if not key:
            return
        with SessionLocal() as session:
            existing = session.query(Preference).filter_by(
                tenant_id=DEFAULT_TENANT_ID, key=key
            ).first()
            now = _now()
            if existing:
                existing.value = str(pref.get("value", ""))
                existing.updated_at_iso = pref.get("updated_at")
                existing.updated_at = now
            else:
                session.add(Preference(
                    tenant_id=DEFAULT_TENANT_ID,
                    key=key,
                    value=str(pref.get("value", "")),
                    updated_at_iso=pref.get("updated_at"),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_preference_db", _write)


# ---------------------------------------------------------------------------
# SOP Summaries
# ---------------------------------------------------------------------------

def save_sop_db(sop: dict) -> None:
    def _write():
        wf_name = str(sop.get("workflow_name") or "")
        if not wf_name:
            return
        with SessionLocal() as session:
            existing = session.query(SOPSummary).filter_by(
                tenant_id=DEFAULT_TENANT_ID, workflow_name=wf_name
            ).first()
            now = _now()
            if existing:
                existing.purpose = sop.get("purpose")
                existing.updated_at_iso = sop.get("updated_at")
                existing.data = _json(sop)
                existing.updated_at = now
            else:
                session.add(SOPSummary(
                    tenant_id=DEFAULT_TENANT_ID,
                    workflow_name=wf_name,
                    purpose=sop.get("purpose"),
                    updated_at_iso=sop.get("updated_at"),
                    data=_json(sop),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_sop_db", _write)


# ---------------------------------------------------------------------------
# Workflow Registry
# ---------------------------------------------------------------------------

def save_workflow_db(wf: dict) -> None:
    def _write():
        wf_name = str(wf.get("workflow_name") or "")
        if not wf_name:
            return
        with SessionLocal() as session:
            existing = session.query(WorkflowRecord).filter_by(
                tenant_id=DEFAULT_TENANT_ID, workflow_name=wf_name
            ).first()
            now = _now()
            if existing:
                existing.description = wf.get("description")
                existing.procedure_name = wf.get("procedure_name")
                existing.safe_for_unattended = bool(wf.get("safe_for_unattended", False))
                existing.data = _json(wf)
                existing.updated_at = now
            else:
                session.add(WorkflowRecord(
                    tenant_id=DEFAULT_TENANT_ID,
                    workflow_name=wf_name,
                    description=wf.get("description"),
                    procedure_name=wf.get("procedure_name"),
                    safe_for_unattended=bool(wf.get("safe_for_unattended", False)),
                    data=_json(wf),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_workflow_db", _write)


# ---------------------------------------------------------------------------
# Workflow Drafts
# ---------------------------------------------------------------------------

def save_draft_db(draft: dict) -> None:
    def _write():
        draft_id = str(draft.get("draft_id") or "")
        if not draft_id:
            return
        with SessionLocal() as session:
            existing = session.get(WorkflowDraft, draft_id)
            now = _now()
            if existing:
                existing.workflow_name = draft.get("workflow_name")
                existing.review_status = draft.get("review_status")
                existing.goal = draft.get("goal")
                existing.created_at_iso = draft.get("created_at")
                existing.data = _json(draft)
                existing.updated_at = now
            else:
                session.add(WorkflowDraft(
                    id=draft_id,
                    tenant_id=DEFAULT_TENANT_ID,
                    workflow_name=draft.get("workflow_name"),
                    review_status=draft.get("review_status"),
                    goal=draft.get("goal"),
                    created_at_iso=draft.get("created_at"),
                    data=_json(draft),
                    created_at=now,
                    updated_at=now,
                ))
            session.commit()
    _safe_write("save_draft_db", _write)
