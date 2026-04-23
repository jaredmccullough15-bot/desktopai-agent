"""
Human recovery context and action handling for paused tasks.

Provides:
- Recovery context schema (checkpoint + diagnostics)
- Structured recovery actions (enum-like command system)
- Recovery state persistence
- Audit logging for operator actions
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


# ── Recovery Actions ──────────────────────────────────────────────────────

class RecoveryAction(str, Enum):
    """Structured recovery commands for smart_sherpa_sync."""
    
    CLOSE_EXTRA_TABS = "close_extra_tabs"
    DISMISS_PRODUCT_REVIEW_MODAL = "dismiss_product_review_modal"
    RETURN_TO_CLIENT_LIST = "return_to_client_list"
    RETRY_LAST_CLIENT = "retry_last_client"
    SKIP_LAST_CLIENT = "skip_last_client"
    RESUME_SYNC = "resume_sync"
    RESTART_FROM_CURRENT_PAGE = "restart_from_current_page"
    RESTART_FROM_CHECKPOINT = "restart_from_last_checkpoint"
    CLOSE_EXTRA_TABS_AND_RETRY = "close_extra_tabs_and_retry_last_client"
    DISMISS_MODAL_AND_RESUME = "dismiss_modal_and_resume"


# ── Recovery Context ──────────────────────────────────────────────────────

@dataclass
class RecoveryContext:
    """Checkpoint and diagnostics for a paused task."""
    
    task_id: str
    workflow_name: str
    paused_at: str  # ISO timestamp
    pause_reason: str  # human-readable reason
    
    # Workflow state
    current_step: int = 0
    last_successful_step: int = 0
    current_url: str = ""
    current_page_number: int = 1
    
    # Client tracking (for smart_sherpa_sync)
    last_client_attempted: str = ""
    last_successful_client: str = ""
    clients_completed: list[str] = field(default_factory=list)
    clients_skipped: list[str] = field(default_factory=list)
    
    # Tab/modal state
    open_tabs_count: int = 0
    open_tab_titles: list[str] = field(default_factory=list)
    active_tab_index: int = 0
    blocking_modal_detected: bool = False
    modal_type: str = ""  # e.g. "product_review", "confirm_dialog"
    
    # Worker context
    worker_name: str = ""
    machine_uuid: str = ""
    
    # Screenshot/diagnostic path
    screenshot_path: str = ""
    
    # Additional error details
    last_error: str = ""
    error_classification: str = ""
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoveryContext:
        """Create from dict."""
        return cls(**data)


@dataclass
class RecoveryActionRequest:
    """Operator request to recover a paused task."""
    
    task_id: str
    action: RecoveryAction  # or str 
    action_id: str = field(default_factory=lambda: str(uuid4()))
    requested_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    requested_by: str = ""  # operator name, optional
    notes: str = ""  # free-text operator comment
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dict."""
        d = asdict(self)
        if isinstance(self.action, RecoveryAction):
            d["action"] = self.action.value
        return d


@dataclass
class RecoveryResult:
    """Outcome of a recovery action execution."""
    
    action_id: str
    task_id: str
    action: str
    success: bool
    executed_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    result_message: str = ""
    error_details: str = ""
    workflow_resumed: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return asdict(self)


# ── Audit Entry ───────────────────────────────────────────────────────────

@dataclass
class RecoveryAuditEntry:
    """Audit log for recovery events."""
    
    entry_id: str = field(default_factory=lambda: str(uuid4()))
    task_id: str = ""
    workflow_name: str = ""
    event_type: str = ""  # "paused", "recovery_requested", "recovery_executed", "resumed", "recovery_failed"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    operator: str = ""
    action: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict."""
        return asdict(self)
