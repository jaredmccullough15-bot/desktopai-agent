"""
models_db.py — SQLAlchemy ORM models for Bill Core.

Design principles (Phase 1):
- Every table has tenant_id (FK → tenants.id) for future multi-tenancy.
- JSON data is stored in a Text "data" column as well as discrete columns
  for the most-queried fields.  This keeps migrations simple while still
  enabling indexed queries later.
- created_at / updated_at on every table.
- No complex relationships yet — plain FKs only.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Workers (registered_workers store)
# ---------------------------------------------------------------------------

class Worker(Base):
    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    machine_uuid: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    machine_name: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=True)
    worker_version: Mapped[str] = mapped_column(Text, nullable=True)
    execution_mode: Mapped[str] = mapped_column(Text, nullable=True)
    current_task_id: Mapped[str] = mapped_column(Text, nullable=True)
    last_seen: Mapped[str] = mapped_column(Text, nullable=True)  # ISO string
    token: Mapped[str] = mapped_column(Text, nullable=True)
    # Full dict serialised as JSON for future-proofing
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Tasks (in-memory list)
# ---------------------------------------------------------------------------

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    task_type: Mapped[str] = mapped_column(Text, nullable=True)
    assigned_machine_uuid: Mapped[str] = mapped_column(Text, nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=True)
    error: Mapped[str] = mapped_column(Text, nullable=True)
    completed_at: Mapped[str] = mapped_column(Text, nullable=True)
    # Full task dict
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Worker Releases
# ---------------------------------------------------------------------------

class WorkerRelease(Base):
    __tablename__ = "worker_releases"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    package_filename: Mapped[str] = mapped_column(Text, nullable=True)
    package_sha256: Mapped[str] = mapped_column(Text, nullable=True)
    release_notes: Mapped[str] = mapped_column(Text, nullable=True)
    upload_time: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Task Reflections
# ---------------------------------------------------------------------------

class TaskReflection(Base):
    __tablename__ = "task_reflections"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    worker_name: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    failure_classification: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Improvement Proposals
# ---------------------------------------------------------------------------

class ImprovementProposal(Base):
    __tablename__ = "improvement_proposals"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    proposal_type: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    confidence: Mapped[str] = mapped_column(Text, nullable=True)
    created_at_iso: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Operational Memory
# ---------------------------------------------------------------------------

class OperationalMemory(Base):
    __tablename__ = "operational_memory"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=True)
    timestamp: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Workflow Registry
# ---------------------------------------------------------------------------

class WorkflowRecord(Base):
    __tablename__ = "workflow_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    procedure_name: Mapped[str] = mapped_column(Text, nullable=True)
    safe_for_unattended: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Workflow Learning Drafts
# ---------------------------------------------------------------------------

class WorkflowDraft(Base):
    __tablename__ = "workflow_drafts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    review_status: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=True)
    created_at_iso: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Interactions (interactive prompts)
# ---------------------------------------------------------------------------

class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    interaction_type: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=True, index=True)
    command: Mapped[str] = mapped_column(Text, nullable=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=True)
    created_at_iso: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Conversation Preferences
# ---------------------------------------------------------------------------

class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at_iso: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# SOP Summaries
# ---------------------------------------------------------------------------

class SOPSummary(Base):
    __tablename__ = "sop_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, ForeignKey("tenants.id"), nullable=False, index=True)
    workflow_name: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=True)
    updated_at_iso: Mapped[str] = mapped_column(Text, nullable=True)
    data: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
