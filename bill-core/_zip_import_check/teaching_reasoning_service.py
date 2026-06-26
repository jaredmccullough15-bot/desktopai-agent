from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


def _clean_text(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip()


def _lower(value: str | None) -> str:
    return _clean_text(value).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _safe_host_path(url_value: str | None) -> str:
    text = _clean_text(url_value)
    if not text:
        return "the page"
    try:
        parsed = urlparse(text)
        host = parsed.hostname or "the site"
        path = parsed.path or "/"
        if path == "/":
            return host
        bits = [bit for bit in path.split("/") if bit]
        if not bits:
            return host
        return f"{host} {bits[-1].replace('-', ' ')} page"
    except Exception:
        return "the page"


def _recent_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned = []
    for raw in actions[-6:]:
        if not isinstance(raw, dict):
            continue
        cleaned.append(
            {
                "type": _lower(raw.get("type")),
                "label": _clean_text(raw.get("label")),
                "selector": _clean_text(raw.get("selector")),
                "url": _clean_text(raw.get("url")),
            }
        )
    return cleaned


def _is_cooldown_active(current_step: dict[str, Any], seconds: int = 7) -> bool:
    stamp = _clean_text(current_step.get("last_reasoned_at"))
    if not stamp:
        return False
    try:
        last = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - last).total_seconds() < seconds
    except Exception:
        return False


def _build_summary(actions: list[dict[str, Any]], message: str, step_order: int) -> tuple[str, str]:
    action_types = [a.get("type", "") for a in actions]
    labels = [_lower(a.get("label")) for a in actions]

    has_nav = "navigate" in action_types
    has_type = "type" in action_types
    has_submit = "submit" in action_types or any("submit" in label for label in labels)
    has_select = "select" in action_types
    has_click = "click" in action_types
    has_search_word = _contains_any(message, ("search", "find", "lookup")) or any(
        _contains_any(label, ("search", "find", "lookup")) for label in labels
    )

    nav_action = next((a for a in reversed(actions) if a.get("type") == "navigate"), None)

    if has_nav and has_search_word:
        return (
            f"I saw you open {_safe_host_path(nav_action.get('url') if nav_action else None)} and search for a client.",
            "Search for the client",
        )
    if has_nav:
        return (
            f"I saw you open {_safe_host_path(nav_action.get('url') if nav_action else None)}.",
            "Open the correct page",
        )
    if has_submit:
        return (
            "I saw you submit this step.",
            "Submit the form",
        )
    if has_select:
        return (
            "I saw you choose an option before continuing.",
            "Choose the correct option",
        )
    if has_type and has_search_word:
        return (
            "I saw you type into a search field to find someone.",
            "Search for the client",
        )
    if has_type and has_click:
        return (
            "I saw you type information and then continue.",
            "Enter required details",
        )
    if has_click:
        return (
            f"I saw you complete Step {step_order} on the page.",
            "Complete the page action",
        )

    if message:
        return (
            f"I think Step {step_order} is about {_clean_text(message).rstrip('.')}.",
            f"Step {step_order}",
        )

    return (
        f"I think you are working on Step {step_order}.",
        f"Step {step_order}",
    )


def _build_question(
    actions: list[dict[str, Any]],
    latest_employee_message: str,
    current_step: dict[str, Any],
) -> str:
    message = _lower(latest_employee_message)
    labels = " ".join(_lower(a.get("label")) for a in actions)
    types = [a.get("type", "") for a in actions]

    if _contains_any(message + " " + labels, ("skip", "skipped", "cancel", "back", "ignore")):
        return "When should Bill skip someone?"

    if "submit" in types or _contains_any(message + " " + labels, ("submit", "save", "finish")):
        return "What should Bill verify before submitting?"

    if _contains_any(message + " " + labels, ("search", "find", "lookup")):
        return "What tells Bill which client to search for?"

    if "select" in types or _contains_any(message + " " + labels, ("dropdown", "radio", "option", "select")):
        return "How should Bill choose the right option?"

    if _contains_any(message + " " + labels, ("modal", "popup", "dialog", "error", "warning", "alert")):
        return "What should Bill do when this message appears?"

    explanation = _clean_text(current_step.get("employee_explanation"))
    if not explanation:
        return "Can you explain this step in simple words?"

    return "I will treat this as the next step. Is that correct?"


def _is_meaningful_group(actions: list[dict[str, Any]], latest_employee_message: str) -> tuple[bool, str]:
    if not actions and not _clean_text(latest_employee_message):
        return False, "no_activity"

    action_types = [a.get("type", "") for a in actions]
    labels = [_lower(a.get("label")) for a in actions]

    has_nav = "navigate" in action_types
    has_submit = "submit" in action_types or any("submit" in label for label in labels)
    has_modal_or_error = any(
        _contains_any(label, ("modal", "popup", "dialog", "error", "warning", "alert"))
        for label in labels
    )

    click_indices = [idx for idx, t in enumerate(action_types) if t == "click"]
    nav_indices = [idx for idx, t in enumerate(action_types) if t == "navigate"]
    click_then_nav = bool(click_indices and nav_indices and min(click_indices) < max(nav_indices))

    has_type = "type" in action_types
    has_follow_up = False
    if has_type:
        for idx, t in enumerate(action_types):
            if t != "type":
                continue
            tail = action_types[idx + 1 :]
            if any(item in {"click", "submit", "select"} for item in tail):
                has_follow_up = True
                break
            tail_labels = labels[idx + 1 :]
            if any(_contains_any(lbl, ("search", "find", "lookup", "submit")) for lbl in tail_labels):
                has_follow_up = True
                break

    repeated_clicks_only = (
        len(action_types) >= 2
        and all(t == "click" for t in action_types)
        and len({label for label in labels if label}) <= 1
    )

    if repeated_clicks_only:
        return False, "repeated_clicks_only"
    if has_nav:
        return True, "navigation"
    if has_submit:
        return True, "submit"
    if click_then_nav:
        return True, "click_then_page_change"
    if has_type and has_follow_up:
        return True, "typing_followed_by_action"
    if has_modal_or_error:
        return True, "modal_or_error"
    if _clean_text(latest_employee_message):
        return True, "employee_explanation"
    return False, "not_meaningful"


def analyze_teaching_reasoning(
    teaching_session: dict[str, Any],
    recent_browser_actions: list[dict[str, Any]],
    latest_employee_message: str,
    current_step: dict[str, Any],
) -> dict[str, Any]:
    actions = _recent_actions(recent_browser_actions)
    message = _clean_text(latest_employee_message)
    step_order = int(current_step.get("order") or (len(teaching_session.get("steps") or []) or 1))

    meaningful, reason = _is_meaningful_group(actions, message)
    summary, suggested_title = _build_summary(actions, message, step_order)
    question = _build_question(actions, message, current_step)

    confidence = 0.45
    if meaningful:
        confidence += 0.2
    if actions:
        confidence += 0.1
    if message:
        confidence += 0.1
    if reason in {"navigation", "submit", "click_then_page_change", "typing_followed_by_action", "modal_or_error"}:
        confidence += 0.1
    confidence = max(0.05, min(0.98, confidence))

    unanswered_question = bool(current_step.get("unanswered_question") or current_step.get("pending_question"))
    cooldown_active = _is_cooldown_active(current_step)

    should_interrupt = meaningful and not unanswered_question and not cooldown_active
    if not meaningful:
        interrupt_reason = reason
    elif unanswered_question:
        interrupt_reason = "pending_question_exists"
    elif cooldown_active:
        interrupt_reason = "cooldown_active"
    else:
        interrupt_reason = reason

    return {
        "bill_summary": summary,
        "suggested_step_title": suggested_title,
        "question": question,
        "confidence": round(confidence, 2),
        "should_interrupt": bool(should_interrupt),
        "reason": interrupt_reason,
    }
