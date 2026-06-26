"""
Tenant Template Service for Bill Core.

Provides all operations on tenant workflow templates:
  - load / save (JSON files)
  - validate
  - list / get by tenant+workflow
  - resolve system / action by key
  - identity scoring
  - deterministic decision rule evaluation
  - integration hooks for future audit workflow
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from tenant_template_schemas import (
    TenantWorkflowTemplate,
    TenantActionTemplate,
    TenantSystemTemplate,
    TenantIdentityPolicy,
    TenantDecisionRule,
    TenantSafetyPolicy,
    TemplateListItem,
    TemplateValidationResult,
    IdentityScoreResult,
    DecisionTestResult,
    RuleCondition,
)

logger = logging.getLogger("bill-core.tenant-template-service")

# ---------------------------------------------------------------------------
# Storage path
# ---------------------------------------------------------------------------

_DEFAULT_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "tenant_templates"

TEMPLATES_DIR = Path(
    os.getenv("BILL_CORE_TENANT_TEMPLATES_DIR") or str(_DEFAULT_TEMPLATES_DIR)
)


def _template_path(tenant_id: str, workflow_id: str) -> Path:
    """Return the canonical JSON file path for a template."""
    safe_tenant = _safe_id(tenant_id)
    safe_workflow = _safe_id(workflow_id)
    return TEMPLATES_DIR / safe_tenant / f"{safe_workflow}.json"


def _safe_id(value: str) -> str:
    """Strip path-traversal characters from identifiers."""
    return "".join(c for c in value if c.isalnum() or c in ("-", "_")).strip("-_")


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

def load_template(tenant_id: str, workflow_id: str) -> TenantWorkflowTemplate:
    """
    Load and parse a tenant workflow template from JSON storage.
    Raises FileNotFoundError if the template does not exist.
    Raises ValueError if JSON is invalid or fails schema validation.
    """
    path = _template_path(tenant_id, workflow_id)
    if not path.exists():
        raise FileNotFoundError(
            f"Template not found: tenant={tenant_id} workflow={workflow_id} path={path}"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in template file {path}: {exc}") from exc
    try:
        return TenantWorkflowTemplate.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"Template schema validation failed for {path}: {exc}") from exc


def save_template(template: TenantWorkflowTemplate) -> Path:
    """
    Persist a template to JSON storage.
    Creates parent directories as needed.
    Returns the path the template was written to.
    """
    path = _template_path(template.tenant_id, template.workflow_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    template.updated_at = datetime.utcnow().isoformat() + "Z"
    path.write_text(
        template.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info(
        "Saved template: tenant=%s workflow=%s path=%s",
        template.tenant_id,
        template.workflow_id,
        path,
    )
    return path


# ---------------------------------------------------------------------------
# List / Get
# ---------------------------------------------------------------------------

def list_templates() -> list[TemplateListItem]:
    """Return lightweight summary records for all templates on disk."""
    items: list[TemplateListItem] = []
    if not TEMPLATES_DIR.exists():
        return items
    for tenant_dir in sorted(TEMPLATES_DIR.iterdir()):
        if not tenant_dir.is_dir():
            continue
        for json_file in sorted(tenant_dir.glob("*.json")):
            try:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                items.append(
                    TemplateListItem(
                        tenant_id=raw.get("tenant_id", tenant_dir.name),
                        workflow_id=raw.get("workflow_id", json_file.stem),
                        workflow_name=raw.get("workflow_name", ""),
                        version=raw.get("version", ""),
                        enabled=bool(raw.get("enabled", True)),
                        tags=list(raw.get("tags") or []),
                        description=raw.get("description", ""),
                    )
                )
            except Exception as exc:
                logger.warning("Skipping unreadable template %s: %s", json_file, exc)
    return items


def list_templates_for_tenant(tenant_id: str) -> list[TemplateListItem]:
    """Return all templates for a specific tenant."""
    return [t for t in list_templates() if t.tenant_id == tenant_id]


def get_template_for_task(tenant_id: str, workflow_id: str) -> TenantWorkflowTemplate | None:
    """
    Integration hook: retrieve the template for an in-progress task.
    Returns None if the template does not exist (non-blocking; caller decides how to handle).
    """
    try:
        return load_template(tenant_id, workflow_id)
    except (FileNotFoundError, ValueError) as exc:
        logger.warning("get_template_for_task: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------

def validate_template(template: TenantWorkflowTemplate) -> TemplateValidationResult:
    """
    Run semantic validation beyond Pydantic schema checks.
    Returns a TemplateValidationResult with errors and warnings lists.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── System keys must be unique ──────────────────────────────────────
    system_keys = [s.system_key for s in template.systems]
    if len(system_keys) != len(set(system_keys)):
        errors.append("Duplicate system_key values found in systems list.")

    # ── Action keys must be unique ──────────────────────────────────────
    action_keys = {a.action_key for a in template.actions}
    dupe_actions = len(template.actions) - len(action_keys)
    if dupe_actions > 0:
        errors.append(f"{dupe_actions} duplicate action_key(s) found in actions list.")

    # ── Decision rules must reference valid action keys ─────────────────
    for rule in template.decision_rules:
        if rule.action_key not in action_keys and rule.action_key != "noop":
            errors.append(
                f"Decision rule '{rule.rule_id}' references unknown action_key '{rule.action_key}'."
            )
        if not rule.conditions:
            warnings.append(
                f"Decision rule '{rule.rule_id}' has no conditions — it will always match."
            )

    # ── Identity policy weight sum ───────────────────────────────────────
    total_weight = sum(f.weight for f in template.identity_policy.fields)
    if total_weight == 0 and template.identity_policy.fields:
        warnings.append("All identity field weights are 0 — identity scoring will always return 0.")
    if total_weight > 100 and len(template.identity_policy.fields) > 1:
        warnings.append(
            f"Total identity field weight is {total_weight}. "
            "If multiple fields match, score may exceed 100 (capped at 100)."
        )

    # ── Threshold sanity ────────────────────────────────────────────────
    ip = template.identity_policy
    if ip.block_below_score > ip.auto_proceed_score:
        errors.append(
            "block_below_score cannot be greater than auto_proceed_score in identity_policy."
        )
    if ip.human_review_score > ip.auto_proceed_score:
        errors.append(
            "human_review_score cannot be greater than auto_proceed_score in identity_policy."
        )

    # ── Action steps reference valid system_keys ────────────────────────
    for action in template.actions:
        for step in action.steps:
            if step.system_key not in system_keys:
                warnings.append(
                    f"Action '{action.action_key}' step {step.step} references "
                    f"unknown system_key '{step.system_key}'."
                )

    # ── Safety: warn about disabled dry_run_default ─────────────────────
    if not template.safety_policy.dry_run_default:
        warnings.append(
            "safety_policy.dry_run_default is False. "
            "Live CRM writes will execute on every run."
        )

    return TemplateValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Resolve helpers
# ---------------------------------------------------------------------------

def resolve_system(template: TenantWorkflowTemplate, system_key: str) -> TenantSystemTemplate | None:
    """Return the system config for a given system_key, or None."""
    for system in template.systems:
        if system.system_key == system_key:
            return system
    return None


def resolve_action(template: TenantWorkflowTemplate, action_key: str) -> TenantActionTemplate | None:
    """Return the action config for a given action_key, or None."""
    for action in template.actions:
        if action.action_key == action_key:
            return action
    return None


def get_action_steps(
    template: TenantWorkflowTemplate, action_key: str
) -> list[dict[str, Any]]:
    """
    Integration hook: return the steps list for an action as plain dicts.
    Returns [] if the action is not found.
    """
    action = resolve_action(template, action_key)
    if action is None:
        logger.warning("get_action_steps: action_key '%s' not found in template.", action_key)
        return []
    return [s.model_dump() for s in action.steps]


# ---------------------------------------------------------------------------
# Identity scoring
# ---------------------------------------------------------------------------

def _normalize(value: Any, case_sensitive: bool, normalize_ws: bool) -> str:
    text = str(value) if value is not None else ""
    if normalize_ws:
        text = " ".join(text.split())
    if not case_sensitive:
        text = text.lower()
    return text


def _fuzzy_score(a: str, b: str) -> float:
    """
    Simple character-level Jaccard similarity.
    Returns a float in [0.0, 1.0].
    No external library required.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def _resolve_aliases(
    policy: TenantIdentityPolicy,
    record: dict[str, Any],
    use_aliases: bool,
) -> dict[str, Any]:
    """
    Return a copy of record with tenant_alias keys resolved to generic_key names.
    e.g. {"keap_id": "123"} → {"external_contact_id": "123"}
    """
    if not use_aliases:
        return dict(record)
    alias_map: dict[str, str] = {}
    for field_def in policy.fields:
        if field_def.tenant_alias:
            alias_map[field_def.tenant_alias] = field_def.generic_key
    resolved: dict[str, Any] = {}
    for k, v in record.items():
        resolved[alias_map.get(k, k)] = v
    return resolved


def score_identity_match(
    template: TenantWorkflowTemplate,
    source_record: dict[str, Any],
    target_contact: dict[str, Any],
    use_aliases: bool = True,
) -> IdentityScoreResult:
    """
    Integration hook: compute an identity match score between source and target.

    The score is the sum of weights for fields that match.
    Score is capped at 100.
    The verdict determines whether the worker should auto-proceed,
    wait for human review, or block the action entirely.
    """
    policy = template.identity_policy
    src = _resolve_aliases(policy, source_record, use_aliases)
    tgt = _resolve_aliases(policy, target_contact, use_aliases)

    total_score = 0
    max_possible = sum(f.weight for f in policy.fields)
    field_results: list[dict[str, Any]] = []

    for field_def in policy.fields:
        src_val = src.get(field_def.generic_key)
        tgt_val = tgt.get(field_def.generic_key)

        if src_val is None or tgt_val is None:
            field_results.append({
                "generic_key": field_def.generic_key,
                "tenant_alias": field_def.tenant_alias,
                "source_value": src_val,
                "target_value": tgt_val,
                "matched": False,
                "match_type": field_def.match_type,
                "weight": field_def.weight,
                "points_awarded": 0,
                "reason": "missing_value",
            })
            continue

        src_norm = _normalize(src_val, field_def.case_sensitive, field_def.normalize_whitespace)
        tgt_norm = _normalize(tgt_val, field_def.case_sensitive, field_def.normalize_whitespace)

        matched = False
        sim_score = 0.0
        reason = ""

        if field_def.match_type in ("exact", "numeric_exact"):
            matched = src_norm == tgt_norm
            sim_score = 1.0 if matched else 0.0
            reason = "exact_match" if matched else "exact_mismatch"

        elif field_def.match_type == "prefix":
            matched = src_norm.startswith(tgt_norm) or tgt_norm.startswith(src_norm)
            sim_score = 1.0 if matched else 0.0
            reason = "prefix_match" if matched else "prefix_mismatch"

        elif field_def.match_type == "fuzzy":
            sim_score = _fuzzy_score(src_norm, tgt_norm)
            matched = sim_score >= 0.75
            reason = f"fuzzy_similarity={sim_score:.2f}"
        else:
            matched = src_norm == tgt_norm
            sim_score = 1.0 if matched else 0.0
            reason = "exact_match_fallback"

        points = field_def.weight if matched else 0
        total_score += points

        field_results.append({
            "generic_key": field_def.generic_key,
            "tenant_alias": field_def.tenant_alias,
            "source_value": str(src_val),
            "target_value": str(tgt_val),
            "matched": matched,
            "match_type": field_def.match_type,
            "similarity": round(sim_score, 3),
            "weight": field_def.weight,
            "points_awarded": points,
            "reason": reason,
        })

    total_score = min(total_score, 100)

    if total_score >= policy.auto_proceed_score:
        verdict = "auto_proceed"
        verdict_note = f"Score {total_score} meets auto_proceed threshold ({policy.auto_proceed_score})."
    elif total_score >= policy.human_review_score:
        verdict = "human_review"
        verdict_note = (
            f"Score {total_score} below auto_proceed ({policy.auto_proceed_score}) "
            f"but meets human_review threshold ({policy.human_review_score})."
        )
    else:
        verdict = "block"
        verdict_note = (
            f"Score {total_score} below block threshold ({policy.block_below_score}). "
            "Action blocked."
        )

    return IdentityScoreResult(
        score=total_score,
        max_possible_score=max_possible,
        field_results=field_results,
        verdict=verdict,
        notes=verdict_note,
    )


# ---------------------------------------------------------------------------
# Decision rule evaluation
# ---------------------------------------------------------------------------

def _get_nested(context: dict[str, Any], dot_path: str) -> Any:
    """Resolve a dot-path like 'audit.status' against a nested dict."""
    parts = dot_path.split(".")
    node: Any = context
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def _evaluate_condition(condition: RuleCondition, context: dict[str, Any]) -> bool:
    """Evaluate one RuleCondition against the audit context dict."""
    actual = _get_nested(context, condition.field)
    op = condition.operator
    expected = condition.value

    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "is_null":
        return actual is None
    if op == "is_not_null":
        return actual is not None
    if op == "in":
        return isinstance(expected, list) and actual in expected
    if op == "not_in":
        return isinstance(expected, list) and actual not in expected
    # Numeric comparisons
    try:
        a = float(actual)  # type: ignore[arg-type]
        b = float(expected)  # type: ignore[arg-type]
        if op == "lt":
            return a < b
        if op == "lte":
            return a <= b
        if op == "gt":
            return a > b
        if op == "gte":
            return a >= b
    except (TypeError, ValueError):
        pass
    return False


def decide_next_action(
    template: TenantWorkflowTemplate,
    audit_context: dict[str, Any],
) -> DecisionTestResult:
    """
    Integration hook: evaluate template decision rules against audit_context.

    Rules are evaluated in priority order (ascending). The FIRST rule whose
    conditions all match (or any, if condition_logic='any') is selected.

    audit_context example:
        {"audit": {"status": "past_due", "agent_of_record": True}}

    Returns a DecisionTestResult with the matched rule and action_key.
    """
    evaluated: list[dict[str, Any]] = []
    rules_sorted = sorted(template.decision_rules, key=lambda r: r.priority)

    for rule in rules_sorted:
        if not rule.conditions:
            # Unconditional rule (always matches); treat as fallback
            result_entry = {
                "rule_id": rule.rule_id,
                "priority": rule.priority,
                "description": rule.description,
                "conditions_evaluated": [],
                "matched": True,
                "reason": "no_conditions_unconditional",
            }
            evaluated.append(result_entry)
            return DecisionTestResult(
                matched_rule_id=rule.rule_id,
                action_key=rule.action_key,
                description=rule.description,
                evaluated_rules=evaluated,
            )

        condition_results = []
        for cond in rule.conditions:
            passed = _evaluate_condition(cond, audit_context)
            condition_results.append({
                "field": cond.field,
                "operator": cond.operator,
                "expected": cond.value,
                "actual": _get_nested(audit_context, cond.field),
                "passed": passed,
            })

        if rule.condition_logic == "all":
            matched = all(c["passed"] for c in condition_results)
        else:  # "any"
            matched = any(c["passed"] for c in condition_results)

        result_entry = {
            "rule_id": rule.rule_id,
            "priority": rule.priority,
            "description": rule.description,
            "condition_logic": rule.condition_logic,
            "conditions_evaluated": condition_results,
            "matched": matched,
        }
        evaluated.append(result_entry)

        if matched:
            return DecisionTestResult(
                matched_rule_id=rule.rule_id,
                action_key=rule.action_key,
                description=rule.description,
                evaluated_rules=evaluated,
            )

    # No rule matched
    return DecisionTestResult(
        matched_rule_id=None,
        action_key=None,
        description="No decision rule matched the audit context.",
        evaluated_rules=evaluated,
    )


# ---------------------------------------------------------------------------
# Import / Export
# ---------------------------------------------------------------------------

def export_template_json(template: TenantWorkflowTemplate) -> str:
    """Serialize template to JSON string (pretty-printed)."""
    return template.model_dump_json(indent=2)


def import_template_json(raw_json: str) -> TenantWorkflowTemplate:
    """
    Parse and validate a JSON string into a TenantWorkflowTemplate.
    Raises ValueError on parse or schema error.
    """
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc
    try:
        return TenantWorkflowTemplate.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Template schema validation failed: {exc}") from exc
