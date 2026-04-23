from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import requests

from playbook_service import find_matching_playbooks, get_all_playbooks, get_playbook
from recovery_suggestion_schemas import (
    RecoverySuggestion,
    RecoverySuggestionBasis,
    RecoverySuggestionWarning,
)

logger = logging.getLogger(__name__)


RETRYABLE_ERROR_TOKENS = ("timeout", "temporar", "network", "connection", "429", "rate limit")
OFF_LIST_URL_TOKENS = ("dashboard", "settings", "profile", "help")


def _normalize_sequence(sequence: list[str]) -> tuple[str, ...]:
    return tuple(str(item or "").strip() for item in sequence if str(item or "").strip())


def _recent_failed_sequences(recovery_actions: list[dict[str, Any]]) -> set[tuple[str, ...]]:
    failed: set[tuple[str, ...]] = set()
    for item in recovery_actions:
        if str(item.get("status") or "") != "failed":
            continue
        action = str(item.get("action") or "").strip()
        if action in {"playbook_auto_sequence", "suggested_action_sequence"}:
            seq = _normalize_sequence(item.get("action_sequence") or [])
            if seq:
                failed.add(seq)
        elif action:
            failed.add((action,))
    return failed


def _is_off_list_state(current_url: str, modal_detected: bool) -> bool:
    if modal_detected:
        return False
    url = (current_url or "").lower()
    if not url:
        return False
    if "client" in url or "member" in url or "search" in url:
        return False
    return any(token in url for token in OFF_LIST_URL_TOKENS)


def _contains_retryable_error(last_error: str) -> bool:
    text = (last_error or "").lower()
    return any(token in text for token in RETRYABLE_ERROR_TOKENS)


def _extract_error_tokens(last_error: str) -> list[str]:
    text = (last_error or "").lower()
    return [token for token in RETRYABLE_ERROR_TOKENS if token in text]


def _suggest_from_rules(
    task_id: str,
    workflow_name: str,
    recovery_context: dict[str, Any],
    recovery_actions: list[dict[str, Any]],
) -> RecoverySuggestion:
    modal_detected = bool(recovery_context.get("blocking_modal_detected"))
    tab_count = int(recovery_context.get("open_tabs_count") or 0)
    current_url = str(recovery_context.get("current_url") or "")
    last_error = str(recovery_context.get("last_error") or "")
    attempts = int(recovery_context.get("recovery_attempt_count") or 0)

    recent_failures = [
        str(a.get("action") or "")
        for a in recovery_actions[-8:]
        if str(a.get("status") or "") == "failed"
    ]
    failed_sequences = _recent_failed_sequences(recovery_actions)

    basis = RecoverySuggestionBasis(
        matched_playbook_id=recovery_context.get("matched_playbook_id"),
        matched_problem_signature=recovery_context.get("matched_problem_signature"),
        modal_detected=modal_detected,
        tab_count=tab_count,
        last_error_contains=_extract_error_tokens(last_error),
        recent_action_failures=[f for f in recent_failures if f],
        workflow_match=True,
        auto_playbook_failed=str(recovery_context.get("playbook_auto_attempt_result") or "").lower() == "failed",
        current_page_type=(recovery_context.get("metadata") or {}).get("page_type") if isinstance(recovery_context.get("metadata"), dict) else None,
        url_hint=current_url[:120] if current_url else None,
    )

    warnings: list[RecoverySuggestionWarning] = []
    source = "rule_based"
    confidence = 0.62
    sequence: list[str] = []
    reasoning = []

    trusted_playbook_sequence: list[str] = []
    try:
        matches = find_matching_playbooks(workflow_name, recovery_context, last_error)
        if matches:
            best = matches[0]
            basis.matched_playbook_id = best.playbook_id
            basis.matched_problem_signature = best.problem_signature
            if best.can_auto_apply:
                playbook = get_playbook(best.playbook_id)
                trusted_playbook_sequence = [
                    str(step.action) for step in ((playbook.action_sequence.actions) if playbook and playbook.action_sequence else [])
                ]
    except Exception as exc:
        logger.debug("suggestion playbook match failed task_id=%s: %s", task_id, exc)

    if trusted_playbook_sequence:
        normalized_playbook = _normalize_sequence(trusted_playbook_sequence)
        if normalized_playbook and normalized_playbook not in failed_sequences:
            sequence = list(normalized_playbook)
            source = "playbook_based"
            confidence = 0.82
            reasoning.append("Trusted learned playbook matched this incident signature.")
        else:
            warnings.append(
                RecoverySuggestionWarning(
                    code="trusted_playbook_recently_failed",
                    message="A learned fix matched but the same sequence already failed in this incident.",
                    severity="high",
                )
            )

    if not sequence:
        if modal_detected and tab_count > 1:
            sequence = ["close_extra_tabs", "dismiss_product_review_modal"]
            confidence = 0.78
            reasoning.append("Blocking modal and extra tabs detected.")
        elif modal_detected:
            sequence = ["dismiss_product_review_modal"]
            confidence = 0.74
            reasoning.append("Blocking modal detected.")
        elif _is_off_list_state(current_url, modal_detected):
            sequence = ["return_to_client_list"]
            confidence = 0.66
            reasoning.append("Context appears off client-list flow.")
        elif _contains_retryable_error(last_error) and recent_failures.count("retry_last_client") < 2:
            sequence = ["retry_last_client"]
            confidence = 0.68
            reasoning.append("Error pattern looks transient and retryable.")
        else:
            same_client_retries = recent_failures.count("retry_last_client")
            if same_client_retries >= 2 or attempts >= 3:
                sequence = ["skip_last_client"]
                confidence = 0.6
                reasoning.append("Repeated failure on current client indicates progress should continue.")
            else:
                sequence = ["return_to_client_list", "retry_last_client"]
                confidence = 0.58
                reasoning.append("Safe reset then retry is likely best next move.")

    normalized = _normalize_sequence(sequence)
    if normalized in failed_sequences and normalized:
        if normalized != ("return_to_client_list",):
            sequence = ["return_to_client_list"]
            confidence = min(confidence, 0.55)
            reasoning.append("Avoided repeating a known failed sequence.")

    if basis.auto_playbook_failed:
        warnings.append(
            RecoverySuggestionWarning(
                code="auto_playbook_already_failed",
                message="Bill already auto-tried a learned fix and it failed for this incident.",
                severity="high",
            )
        )
    if "retry_last_client" in sequence and recent_failures.count("retry_last_client") >= 2:
        warnings.append(
            RecoverySuggestionWarning(
                code="retry_may_repeat_failure",
                message="Retry may repeat the same failure pattern.",
                severity="warning",
            )
        )
    if "skip_last_client" in sequence:
        warnings.append(
            RecoverySuggestionWarning(
                code="skip_is_destructive",
                message="Skip Last Client may permanently bypass this client.",
                severity="high",
            )
        )
    if "return_to_client_list" in sequence:
        warnings.append(
            RecoverySuggestionWarning(
                code="return_discards_page_state",
                message="Return to Client List may discard in-page state.",
                severity="warning",
            )
        )
    if "close_extra_tabs" in sequence:
        warnings.append(
            RecoverySuggestionWarning(
                code="close_tabs_scope_warning",
                message="Close Extra Tabs can affect operator browser context if scope is wrong.",
                severity="warning",
            )
        )

    if not reasoning:
        reasoning.append("Deterministic recovery rules selected the safest next action.")

    primary_action = sequence[0] if sequence else "return_to_client_list"

    return RecoverySuggestion(
        task_id=task_id,
        workflow_name=workflow_name,
        recommended_action_sequence=sequence or ["return_to_client_list"],
        primary_action=primary_action,
        confidence=confidence,
        reasoning_summary=" ".join(reasoning),
        based_on=basis,
        warnings=warnings,
        source=source,
    )


def _maybe_ai_rank(suggestion: RecoverySuggestion, recovery_context: dict[str, Any]) -> RecoverySuggestion:
    if os.getenv("RECOVERY_SUGGESTION_AI_ENABLED", "0").strip() != "1":
        return suggestion

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return suggestion

    try:
        payload = {
            "model": os.getenv("RECOVERY_SUGGESTION_AI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": "You are a recovery ranking helper. Return strict JSON only.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task_id": suggestion.task_id,
                            "workflow_name": suggestion.workflow_name,
                            "sequence": suggestion.recommended_action_sequence,
                            "last_error": recovery_context.get("last_error"),
                            "modal_detected": recovery_context.get("blocking_modal_detected"),
                            "open_tabs_count": recovery_context.get("open_tabs_count"),
                            "current_url": recovery_context.get("current_url"),
                            "instruction": "Return JSON with keys confidence_adjustment (-0.1..0.1) and explanation (max 200 chars).",
                        }
                    ),
                },
            ],
            "temperature": 0.1,
        }
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=6,
        )
        response.raise_for_status()
        data = response.json()
        content = (
            (((data or {}).get("choices") or [{}])[0].get("message") or {}).get("content")
            or "{}"
        )
        parsed = json.loads(content)
        delta = float(parsed.get("confidence_adjustment") or 0.0)
        delta = max(-0.1, min(0.1, delta))
        explanation = str(parsed.get("explanation") or "").strip()

        suggestion.confidence = max(0.1, min(0.98, float(suggestion.confidence) + delta))
        if explanation:
            suggestion.reasoning_summary = f"{suggestion.reasoning_summary} AI note: {explanation}".strip()
        suggestion.source = "ai_assisted"
    except Exception as exc:
        logger.debug("AI suggestion ranking skipped: %s", exc)

    return suggestion


def generate_recovery_suggestion(
    task: dict[str, Any],
    candidate_playbooks: list[dict[str, Any]] | None = None,
    trusted_playbooks: list[dict[str, Any]] | None = None,
) -> RecoverySuggestion:
    task_id = str(task.get("id") or "")
    payload = task.get("payload") or {}
    recovery_context = task.get("recovery_context") or {}
    recovery_actions = task.get("recovery_actions") or []
    workflow_name = (
        str(recovery_context.get("workflow_name") or "").strip()
        or str(payload.get("workflow_name") or payload.get("task_type") or "unknown").strip()
        or "unknown"
    )

    suggestion = _suggest_from_rules(task_id, workflow_name, recovery_context, recovery_actions)

    # Attach quick playbook availability hints for UI/context diagnostics.
    if candidate_playbooks is None or trusted_playbooks is None:
        playbooks = get_all_playbooks(workflow_name=workflow_name, active_only=True)
        candidate_playbooks = [p.to_dict() if hasattr(p, "to_dict") else p for p in playbooks if str(getattr(p, "status", "")) == "candidate"]
        trusted_playbooks = [p.to_dict() if hasattr(p, "to_dict") else p for p in playbooks if str(getattr(p, "status", "")) == "trusted"]

    suggestion.based_on.workflow_match = bool(workflow_name and workflow_name != "unknown")
    if suggestion.based_on.current_page_type is None and current_url := str(recovery_context.get("current_url") or ""):
        suggestion.based_on.current_page_type = "client_list" if "client" in current_url.lower() else "unknown"

    suggestion = _maybe_ai_rank(suggestion, recovery_context)

    # Keep metadata traceable and deterministic for incident timeline.
    suggestion.generated_at = datetime.utcnow().isoformat()
    return suggestion


def queue_suggested_fix_actions(
    task: dict[str, Any],
    suggestion: RecoverySuggestion,
    operator_notes: str = "",
) -> list[dict[str, Any]]:
    from uuid import uuid4

    actions = task.setdefault("recovery_actions", [])
    queued: list[dict[str, Any]] = []
    sequence = [a for a in suggestion.recommended_action_sequence if a]
    if not sequence:
        return queued

    # Queue as sequence when more than one step so worker preserves order/stop-on-failure.
    if len(sequence) > 1:
        item = {
            "action_id": str(uuid4()),
            "action": "suggested_action_sequence",
            "requested_at": datetime.utcnow().isoformat(),
            "operator_notes": operator_notes,
            "status": "pending",
            "source": "suggested_fix",
            "suggestion_id": suggestion.suggestion_id,
            "action_sequence": sequence,
            "stop_on_first_failure": True,
        }
        actions.append(item)
        queued.append(item)
    else:
        item = {
            "action_id": str(uuid4()),
            "action": sequence[0],
            "requested_at": datetime.utcnow().isoformat(),
            "operator_notes": operator_notes,
            "status": "pending",
            "source": "suggested_fix",
            "suggestion_id": suggestion.suggestion_id,
        }
        actions.append(item)
        queued.append(item)

    task["recovery_last_action"] = sequence[0]
    task["updated_at"] = datetime.utcnow().isoformat()
    return queued
