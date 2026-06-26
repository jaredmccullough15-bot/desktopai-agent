"""
error_explainer.py
------------------
Converts technical failures into plain-English explanations for non-technical operators.
Provides classification, explanation generation, and similar-failure memory lookup.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

CATEGORIES = {
    "selector_issue",
    "pagination_issue",
    "session_login",
    "timeout",
    "network",
    "unknown",
}

# Ordered: more specific patterns first
_CLASSIFICATION_RULES: list[tuple[list[str], str]] = [
    # Session / login
    (["login", "session", "unauthorized", "forbidden", "401", "403", "not logged in", "authentication"], "session_login"),
    # Pagination
    (["pagination", "next page", "go to next page", "MuiTablePagination", "button:nth-child(2)", "paginat"], "pagination_issue"),
    # Timeout (after pagination so "intercepts pointer" timeout gets pagination if matched above)
    (["timeout", "timed out", "time out", "exceeded"], "timeout"),
    # Selector
    (["selector", "locator", "element", "not found", "no such", "subtree intercepts", "intercepts pointer"], "selector_issue"),
    # Network
    (["network", "dns", "connection", "refused", "reset", "econnreset", "fetch failed", "unreachable"], "network"),
]


def classify_error(error_text: str | None) -> str:
    """Return one of the CATEGORIES constants for the given error text."""
    lowered = str(error_text or "").lower()
    if not lowered:
        return "unknown"
    for keywords, category in _CLASSIFICATION_RULES:
        if any(kw in lowered for kw in keywords):
            return category
    return "unknown"


# ---------------------------------------------------------------------------
# Explanation generation
# ---------------------------------------------------------------------------

_EXPLANATIONS: dict[str, dict[str, str]] = {
    "timeout": {
        "what_happened": "The automation ran out of time waiting for the page to respond.",
        "likely_cause": "The website was slow to load, or a pop-up / dialog appeared and blocked the normal flow.",
        "meaning": "No data was processed during this run. The task stopped before completing.",
        "recommended_next_action": "Retry the task during off-peak hours. If it keeps failing, reduce the number of records processed per run.",
    },
    "selector_issue": {
        "what_happened": "The automation could not find or click a button or field on the page.",
        "likely_cause": "The website may have updated its layout, or the page did not fully load before the automation tried to act.",
        "meaning": "The task could not complete the required step. No changes were made after the point of failure.",
        "recommended_next_action": "Check whether the website looks different than usual. A site update may require an automation update.",
    },
    "pagination_issue": {
        "what_happened": "The automation got stuck trying to move to the next page of results.",
        "likely_cause": "A dialog or overlay appeared on the screen and blocked the 'Next page' button from being clicked.",
        "meaning": "Only the records visible before the blocked page were processed. The remaining pages were skipped.",
        "recommended_next_action": "Close any open dialogs or pop-ups on the worker screen and retry. If this happens repeatedly, it may need a workflow fix.",
    },
    "session_login": {
        "what_happened": "The automation was not logged in or the login session had expired.",
        "likely_cause": "The worker's browser session timed out, or login credentials are no longer valid.",
        "meaning": "No work was performed. The site rejected the automation because it was not authenticated.",
        "recommended_next_action": "Log the worker back into the website manually, then retry the task.",
    },
    "network": {
        "what_happened": "The automation could not reach the website due to a connection problem.",
        "likely_cause": "The internet connection on the worker machine was interrupted, or the website was temporarily unavailable.",
        "meaning": "No data was processed. The task failed before it could start doing any work.",
        "recommended_next_action": "Check that the worker machine has an internet connection and the website is accessible, then retry.",
    },
    "unknown": {
        "what_happened": "The task failed for an unexpected reason.",
        "likely_cause": "An error occurred that does not match a known pattern. It may be a temporary issue or an edge case.",
        "meaning": "The task did not complete. Check the technical details for more information.",
        "recommended_next_action": "Review the error details below and retry once. If it keeps failing, contact support.",
    },
}


def generate_explanation(
    category: str,
    error_text: str | None = None,
    similar_failure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Return a plain-English explanation dict for the given failure category.
    Optionally references a previous similar failure from memory.
    """
    base = _EXPLANATIONS.get(category, _EXPLANATIONS["unknown"])
    result: dict[str, Any] = {
        "what_happened": base["what_happened"],
        "likely_cause": base["likely_cause"],
        "meaning": base["meaning"],
        "recommended_next_action": base["recommended_next_action"],
        "category": category,
    }

    if similar_failure:
        prev_action = str(similar_failure.get("recommended_next_action") or "").strip()
        prev_fix = str(similar_failure.get("potential_fix") or "").strip()
        prev_worker = str(similar_failure.get("worker_name") or "").strip()
        prev_ts = str(similar_failure.get("timestamp") or "").strip()[:10]
        hint_parts: list[str] = []
        if prev_worker and prev_ts:
            hint_parts.append(f"This matches a previous failure on {prev_worker} ({prev_ts}).")
        elif prev_ts:
            hint_parts.append(f"This matches a previous failure on {prev_ts}.")
        if prev_fix:
            hint_parts.append(f"It was resolved by: {prev_fix}")
        elif prev_action:
            hint_parts.append(f"The suggested fix was: {prev_action}")
        if hint_parts:
            result["memory_hint"] = " ".join(hint_parts)

    return result


# ---------------------------------------------------------------------------
# Confidence scoring
# ---------------------------------------------------------------------------

def score_confidence(category: str, error_text: str | None) -> float:
    """Return a 0.0–1.0 confidence score for the classification."""
    if category == "unknown":
        return 0.4
    lowered = str(error_text or "").lower()
    # Count how many keywords matched
    matched_kws = 0
    for keywords, cat in _CLASSIFICATION_RULES:
        if cat == category:
            matched_kws = sum(1 for kw in keywords if kw in lowered)
            break
    if matched_kws >= 3:
        return 0.92
    if matched_kws == 2:
        return 0.80
    if matched_kws == 1:
        return 0.65
    return 0.55


# ---------------------------------------------------------------------------
# Human summary builder (used in reflection records)
# ---------------------------------------------------------------------------

def build_human_summary(
    category: str,
    workflow_name: str | None,
    worker_name: str | None,
    status: str,
) -> str:
    """One-sentence plain-English summary for a reflection record."""
    wf = (workflow_name or "workflow").replace("_", " ")
    wk = worker_name or "unknown worker"
    if status == "completed":
        return f"The {wf} task ran successfully on {wk}."
    expl = _EXPLANATIONS.get(category, _EXPLANATIONS["unknown"])
    return f"The {wf} task on {wk} failed: {expl['what_happened']}"


# ---------------------------------------------------------------------------
# Similar-failure lookup helper (called from main.py with access to store)
# ---------------------------------------------------------------------------

def find_similar_failure(
    reflections: list[dict[str, Any]],
    category: str,
    workflow_name: str | None,
    current_task_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any] | None:
    """
    Search recent reflections for a past failure of the same category and workflow.
    Returns the most recent match, or None.
    """
    candidates = [
        item for item in reflections
        if str(item.get("status") or "") == "failed"
        and str(item.get("task_id") or "") != str(current_task_id or "")
        and (
            not workflow_name
            or str(item.get("workflow_name") or "").lower() == str(workflow_name).lower()
        )
        and (
            str(item.get("failure_classification") or classify_error(item.get("supporting_evidence")))
            == category
        )
    ]
    # Sort most recent first
    candidates.sort(key=lambda x: str(x.get("timestamp") or ""), reverse=True)
    return candidates[0] if candidates else None
