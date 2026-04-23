from __future__ import annotations

import os
import time
from typing import Any

from voice_schemas import VoiceEventPayload

DEFAULT_EVENT_MESSAGES: dict[str, tuple[str, str, str, str]] = {
    "recovery_stuck": (
        "recovery",
        "I ran into an issue and need help to continue.",
        "empathetic",
        "empathetic",
    ),
    "suggested_fix_available": (
        "recovery",
        "I found a suggested fix. Please review and apply it if it looks right.",
        "helpful",
        "default",
    ),
    "recovery_succeeded": (
        "recovery",
        "The issue is resolved. Continuing now.",
        "confident",
        "default",
    ),
    "workflow_started": (
        "workflow",
        "Starting the requested workflow now.",
        "helpful",
        "default",
    ),
    "workflow_completed": (
        "workflow",
        "The workflow is complete.",
        "confident",
        "energetic",
    ),
    "warning_risk": (
        "warning",
        "Warning. I detected a risk that may need your attention.",
        "alert",
        "urgent",
    ),
}

_last_spoken_by_category: dict[str, float] = {}


def _truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_event_voice_enabled() -> bool:
    return _truthy(os.getenv("BILL_VOICE_EVENTS_ENABLED"), default=True)


def get_enabled_categories() -> list[str]:
    raw = (os.getenv("BILL_VOICE_EVENT_CATEGORIES") or "workflow,recovery,warning").strip()
    values = [part.strip().lower() for part in raw.split(",") if part.strip()]
    return values or ["workflow", "recovery", "warning"]


def get_rate_limit_seconds() -> float:
    raw = (os.getenv("BILL_VOICE_EVENT_MIN_INTERVAL_SECONDS") or "4").strip()
    try:
        value = float(raw)
    except ValueError:
        return 4.0
    return max(0.0, min(120.0, value))


def _passes_rate_limit(category: str) -> bool:
    now = time.monotonic()
    min_interval = get_rate_limit_seconds()
    last = _last_spoken_by_category.get(category)
    if last is not None and (now - last) < min_interval:
        return False
    _last_spoken_by_category[category] = now
    return True


def build_event_voice_payload(event_type: str, context: dict[str, Any] | None = None, override_text: str | None = None) -> VoiceEventPayload | None:
    if not is_event_voice_enabled():
        return None

    definition = DEFAULT_EVENT_MESSAGES.get(event_type)
    if definition is None:
        return None

    category, default_text, emotion, style_profile = definition
    if category not in get_enabled_categories():
        return None
    if not _passes_rate_limit(category):
        return None

    ctx = context or {}
    workflow_name = str(ctx.get("workflow_name") or "").strip()
    task_id = str(ctx.get("task_id") or "").strip()

    text = (override_text or default_text).strip()
    if workflow_name and event_type in {"workflow_started", "workflow_completed"}:
        text = f"{text.rstrip('.')} Workflow: {workflow_name}."
    elif task_id and event_type.startswith("recovery"):
        text = f"{text.rstrip('.')} Task ID: {task_id}."

    return VoiceEventPayload(
        event_type=event_type,
        category=category,
        text=text,
        emotion=emotion,  # type: ignore[arg-type]
        style_profile=style_profile,  # type: ignore[arg-type]
    )
