"""
timeout_recovery.py
-------------------
Timeout classification and workflow-level recovery ladder for Bill Core.

Recovery Ladder (ordered):
  1. retry_step          - Retry the failing step with the same parameters
  2. local_recovery      - Reload page / clear dialogs, then retry
  3. checkpoint_resume   - Resume from last safe checkpoint in the workflow
  4. task_restart        - Restart the full task (if allowed by policy)
  5. needs_human_help    - Escalate to human operator
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Timeout type classification
# ---------------------------------------------------------------------------

_TIMEOUT_TYPE_RULES: list[tuple[list[str], str]] = [
    # Page / navigation load timeouts (check these first — most specific)
    (
        [
            "navigation",
            "net::err",
            "frame.navigate",
            "page timeout",
            "err_connection",
            "err_name_not_resolved",
            "err_timed_out",
            "load event fired",
            "domcontentloaded",
        ],
        "page_load_timeout",
    ),
    # State transition — expected UI state never arrived
    (
        [
            "expected state",
            "state transition",
            "text not found",
            "text to be visible",
            "expected to contain",
            "waitforfunction",
            "element to be hidden",
            "still absent",
            "not appearing",
        ],
        "state_transition_timeout",
    ),
    # Step-level — a specific selector/action timed out
    (
        [
            "waitforselector",
            "locator.click",
            "locator.fill",
            "locator.wait",
            "waiting for selector",
            "element not found",
            "timeout",
            "timed out",
            "time out",
            "exceeded",
        ],
        "step_timeout",
    ),
]


def classify_timeout_type(error_text: str | None) -> str:
    """Classify a timeout error into one of the 4 timeout subtypes."""
    lowered = str(error_text or "").lower()
    if not lowered:
        return "step_timeout"
    for keywords, ttype in _TIMEOUT_TYPE_RULES:
        if any(kw in lowered for kw in keywords):
            return ttype
    return "step_timeout"


def is_repeated_persistent(state: "TaskRecoveryState") -> bool:
    """True when the same task has accumulated 3+ timeout failures — a persistent pattern."""
    return state.total_timeout_hits >= 3


# ---------------------------------------------------------------------------
# Timeout policy
# ---------------------------------------------------------------------------


@dataclass
class TimeoutPolicy:
    """Per-workflow timeout recovery configuration."""

    max_step_retries: int = 2
    max_recovery_attempts: int = 3
    restart_allowed: bool = True
    prefer_human_escalation: bool = False
    step_timeout_ms: int = 20000
    page_timeout_ms: int = 45000
    checkpoint_after_n_steps: int = 5

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TimeoutPolicy":
        return cls(
            max_step_retries=int(d.get("max_step_retries", 2)),
            max_recovery_attempts=int(d.get("max_recovery_attempts", 3)),
            restart_allowed=bool(d.get("restart_allowed", True)),
            prefer_human_escalation=bool(d.get("prefer_human_escalation", False)),
            step_timeout_ms=int(d.get("step_timeout_ms", 20000)),
            page_timeout_ms=int(d.get("page_timeout_ms", 45000)),
            checkpoint_after_n_steps=int(d.get("checkpoint_after_n_steps", 5)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_step_retries": self.max_step_retries,
            "max_recovery_attempts": self.max_recovery_attempts,
            "restart_allowed": self.restart_allowed,
            "prefer_human_escalation": self.prefer_human_escalation,
            "step_timeout_ms": self.step_timeout_ms,
            "page_timeout_ms": self.page_timeout_ms,
            "checkpoint_after_n_steps": self.checkpoint_after_n_steps,
        }


DEFAULT_POLICY = TimeoutPolicy()


# ---------------------------------------------------------------------------
# Recovery ladder
# ---------------------------------------------------------------------------

RECOVERY_LADDER: list[str] = [
    "retry_step",        # 1. Retry the exact step that timed out
    "local_recovery",    # 2. Reload page / clear dialogs, then retry
    "checkpoint_resume", # 3. Resume from last safe checkpoint
    "task_restart",      # 4. Restart the whole task from step 1
    "needs_human_help",  # 5. Escalate — all automated recovery exhausted
]

_RECOVERY_DESCRIPTIONS: dict[str, str] = {
    "retry_step": "Retry the current step with the same parameters.",
    "local_recovery": "Reload the page, dismiss any open dialogs, wait for the page to stabilize, then retry.",
    "checkpoint_resume": "Return to the last saved checkpoint in the workflow and resume from there.",
    "task_restart": "Restart the entire task from the beginning (allowed by workflow policy).",
    "needs_human_help": "All automated recovery has been exhausted — human intervention is required.",
}

# Payload hints merged into retry tasks so workers can act on them
_RECOVERY_PAYLOAD_HINTS: dict[str, dict[str, Any]] = {
    "retry_step": {
        "recovery_action": "retry_step",
        "clear_overlay": False,
    },
    "local_recovery": {
        "recovery_action": "local_recovery",
        "clear_overlay": True,
        "reload_before_start": True,
    },
    "checkpoint_resume": {
        "recovery_action": "checkpoint_resume",
        "resume_from_checkpoint": True,
    },
    "task_restart": {
        "recovery_action": "task_restart",
        "force_fresh_context": True,
    },
}


def next_recovery_action(attempt_count: int, policy: TimeoutPolicy) -> str:
    """
    Return the next recovery action to try.

    ``attempt_count`` is 0 on the very first timeout (no prior recovery attempted).
    Each call should receive the count of attempts already made (i.e. already logged).
    """
    ladder = list(RECOVERY_LADDER)
    if not policy.restart_allowed or policy.prefer_human_escalation:
        ladder = [a for a in ladder if a != "task_restart"]
    # Take only as many rungs as max_recovery_attempts allows, then always escalate
    usable = ladder[: policy.max_recovery_attempts] + ["needs_human_help"]
    if attempt_count < len(usable):
        return usable[attempt_count]
    return "needs_human_help"


def build_recovery_payload(
    original_payload: dict[str, Any],
    action: str,
    attempt_number: int,
    origin_task_id: str | None = None,
) -> dict[str, Any]:
    """Build an enriched task payload for the auto-retry task.

    ``origin_task_id`` is the ID of the first task in the recovery chain.
    It is propagated to every retry task so that all failures in the chain
    share a single ``TaskRecoveryState`` (keyed by the origin ID).
    """
    payload = dict(original_payload)
    hints = _RECOVERY_PAYLOAD_HINTS.get(action, {})
    payload.update(hints)
    payload["recovery_attempt_number"] = attempt_number
    # Preserve the recovery chain origin so the shared recovery state is used
    if origin_task_id:
        payload["recovery_origin_task_id"] = origin_task_id

    # For local_recovery on browser_workflow tasks: prepend a page reload step
    if action == "local_recovery" and payload.get("task_type") == "browser_workflow":
        steps = list(payload.get("steps") or [])
        if steps and steps[0].get("action") != "reload_page":
            steps.insert(0, {"action": "reload_page", "timeout_ms": 15000})
            payload["steps"] = steps

    return payload


# ---------------------------------------------------------------------------
# Per-task recovery state tracker (in-memory, keyed by task_id)
# ---------------------------------------------------------------------------


@dataclass
class TaskRecoveryState:
    task_id: str
    workflow_name: str | None
    timeout_type: str = "step_timeout"
    attempt_log: list[dict[str, Any]] = field(default_factory=list)
    total_timeout_hits: int = 0
    last_recovery_action: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def record_attempt(
        self,
        action: str,
        error_text: str,
        step_name: str | None = None,
    ) -> None:
        self.total_timeout_hits += 1
        self.last_recovery_action = action
        self.updated_at = datetime.utcnow().isoformat()
        self.attempt_log.append(
            {
                "attempt_number": self.total_timeout_hits,
                "action": action,
                "action_description": _RECOVERY_DESCRIPTIONS.get(action, action),
                "error_text": (error_text or "")[:400],
                "step_name": step_name,
                "timestamp": self.updated_at,
            }
        )


# Global in-memory registry keyed by task_id
_recovery_tracker: dict[str, TaskRecoveryState] = {}


def get_or_create_recovery_state(
    task_id: str,
    workflow_name: str | None,
) -> TaskRecoveryState:
    if task_id not in _recovery_tracker:
        _recovery_tracker[task_id] = TaskRecoveryState(
            task_id=task_id,
            workflow_name=workflow_name,
        )
    return _recovery_tracker[task_id]


def clear_recovery_state(task_id: str) -> None:
    _recovery_tracker.pop(task_id, None)


# ---------------------------------------------------------------------------
# Reflection narrative builder
# ---------------------------------------------------------------------------


def build_timeout_reflection_fields(
    state: TaskRecoveryState,
    final_action: str,
    error_text: str | None,
    policy: TimeoutPolicy,
) -> dict[str, Any]:
    """Return extra fields to be merged into a task reflection record for timeouts."""
    what_timed_out = _infer_what_timed_out(error_text)
    recovery_tried = [entry["action"] for entry in state.attempt_log]
    restart_attempted = "task_restart" in recovery_tried
    still_failed = final_action == "needs_human_help"

    # Build plain-English narrative covering all 5 required reflection points
    narrative_parts: list[str] = [
        f"What timed out: {what_timed_out}.",
        f"Timeout type classified as: {state.timeout_type.replace('_', ' ')}.",
    ]

    if is_repeated_persistent(state):
        narrative_parts.append(
            f"This is a repeated persistent timeout — the task timed out {state.total_timeout_hits} times."
        )

    if recovery_tried:
        tried_readable = "; ".join(
            f"attempt {i + 1}: {_RECOVERY_DESCRIPTIONS.get(a, a)}"
            for i, a in enumerate(recovery_tried)
        )
        narrative_parts.append(
            f"Automatic recovery was tried {len(recovery_tried)} time(s): {tried_readable}."
        )
    else:
        narrative_parts.append(
            "No prior automatic recovery was attempted before this escalation."
        )

    if restart_attempted:
        narrative_parts.append(
            "A full task restart was attempted as part of the recovery sequence."
        )

    if still_failed:
        why = _explain_why_still_failed(
            state.timeout_type, state.total_timeout_hits, policy
        )
        narrative_parts.append(f"Why it still failed: {why}")
        narrative_parts.append(
            "Task escalated to needs_human_help — operator action is required."
        )
    elif final_action != "needs_human_help":
        narrative_parts.append(
            f"Recovery in progress — next action queued: "
            f"{_RECOVERY_DESCRIPTIONS.get(final_action, final_action)}"
        )

    return {
        "timeout_type": state.timeout_type,
        "timeout_recovery_attempts": len(state.attempt_log),
        "timeout_recovery_log": state.attempt_log,
        "timeout_restart_attempted": restart_attempted,
        "timeout_narrative": " ".join(narrative_parts),
        "timeout_policy_applied": policy.to_dict(),
    }


def _infer_what_timed_out(error_text: str | None) -> str:
    lowered = str(error_text or "").lower()
    m = re.search(r"waitforselector\(['\"]([^'\"]{1,80})['\"]", lowered)
    if m:
        return f"selector '{m.group(1)}'"
    m = re.search(r"locator\.(?:click|fill|wait|check|type)\(['\"]([^'\"]{1,80})['\"]", lowered)
    if m:
        return f"element '{m.group(1)}'"
    if any(k in lowered for k in ["navigation", "net::err", "page timeout", "err_timed_out"]):
        return "page navigation or page load"
    if any(k in lowered for k in ["state transition", "expected text", "text not found", "still absent"]):
        return "expected UI state transition"
    # Try to capture context around the word "timeout"
    m = re.search(r"(.{0,30})timeout", lowered)
    if m and m.group(1).strip():
        ctx = m.group(1).strip().split()[-3:]
        return f"operation near: '{' '.join(ctx)}...'"
    return "an automated step (see error details)"


def _explain_why_still_failed(
    timeout_type: str,
    hit_count: int,
    policy: TimeoutPolicy,
) -> str:
    if hit_count > policy.max_recovery_attempts:
        return (
            f"The timeout repeated {hit_count} time(s), exceeding the maximum "
            f"configured recovery attempts ({policy.max_recovery_attempts})."
        )
    if timeout_type == "page_load_timeout":
        return (
            "The target page continued to fail to load within the allowed time "
            "across all recovery attempts."
        )
    if timeout_type == "state_transition_timeout":
        return (
            "The expected UI state never appeared, even after page reload "
            "and checkpoint resume."
        )
    if timeout_type == "repeated_persistent_timeout":
        return (
            "Every rung of the recovery ladder encountered the same timeout pattern."
        )
    return (
        "The step continued to time out regardless of the recovery strategy applied."
    )
