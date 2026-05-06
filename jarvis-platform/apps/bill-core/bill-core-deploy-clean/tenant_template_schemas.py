"""
Tenant Template Schemas for Bill Core.

Defines the data model for multi-tenant, configurable workflow automation.
Bill Core stays generic; all tenant-specific system names, CRM fields, and
decision rules live in these templates.

Key design principles:
- No hardcoded Keap/Infusionsoft/Salesforce logic here.
- Systems are identified by generic system_key (e.g. "crm", "carrier_portal").
- Identity fields use generic names (external_contact_id, marketplace_id, policy_number).
- Tenant-specific aliases map their real field names to generic names.
- Decision rules are data-driven (not LLM-driven).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Selector definitions
# ---------------------------------------------------------------------------

class SelectorSet(BaseModel):
    """CSS / Playwright selectors for a system's key UI elements."""
    search_input: str | None = None
    search_button: str | None = None
    results_container: str | None = None
    result_row: str | None = None
    next_page_button: str | None = None
    no_results_indicator: str | None = None
    # Freeform for system-specific elements
    extra: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Extraction field definition
# ---------------------------------------------------------------------------

class ExtractionField(BaseModel):
    """Describes how to extract a value from a page."""
    field_key: str                          # generic name, e.g. "paid_through_date"
    display_label: str | None = None        # human label, e.g. "Paid Through"
    selector: str | None = None            # CSS/Playwright selector
    attribute: str | None = None           # DOM attribute, e.g. "textContent", "value", "data-date"
    transform: str | None = None           # optional: "strip", "date_mdy", "date_ymd", "lowercase"
    required: bool = False
    notes: str | None = None


# ---------------------------------------------------------------------------
# Navigation step definition
# ---------------------------------------------------------------------------

class NavigationStep(BaseModel):
    """One step in a multi-step navigation sequence."""
    step: int
    action: Literal["open_url", "click_selector", "type_text", "wait_for_element",
                    "take_screenshot", "wait_ms", "select_option", "clear_and_type"]
    url: str | None = None
    selector: str | None = None
    value: str | None = None           # may reference {identity.field_key} tokens
    timeout_ms: int | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# System template
# ---------------------------------------------------------------------------

class TenantSystemTemplate(BaseModel):
    """
    Configuration for one external system used in a tenant workflow.

    system_key is the stable generic reference (e.g. "crm", "carrier_portal").
    system_name is the human/brand name (e.g. "Keap", "Ambetter Portal").
    """
    system_key: str                        # stable generic key: "crm" | "carrier_portal" | "healthsherpa" | "trackvia"
    system_name: str                       # human name: "Keap", "Salesforce", "Ambetter", etc.
    base_url: str = ""
    login_url: str | None = None
    selectors: SelectorSet = Field(default_factory=SelectorSet)
    search_strategy: str = "url_param"    # "url_param" | "form_submit" | "api_call"
    extraction_fields: list[ExtractionField] = Field(default_factory=list)
    navigation_steps: list[NavigationStep] = Field(default_factory=list)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Action step definition (within an action template)
# ---------------------------------------------------------------------------

class ActionStep(BaseModel):
    """A single step inside an action template."""
    step: int
    system_key: str                        # which system this step targets
    action: str                            # browser_workflow action or api_call
    selector: str | None = None
    value: str | None = None              # may reference {audit.*} or {identity.*} tokens
    url: str | None = None
    timeout_ms: int | None = None
    description: str | None = None
    on_failure: Literal["stop", "skip", "escalate"] = "stop"


# ---------------------------------------------------------------------------
# Action template
# ---------------------------------------------------------------------------

class TenantActionTemplate(BaseModel):
    """
    A named, reusable action that can be triggered by decision rules.

    action_key uses dot notation: crm.mark_past_due, carrier.lookup_client
    action_type distinguishes UI automation from API calls and manual gates.
    """
    action_key: str                        # e.g. "crm.mark_past_due"
    action_type: Literal[
        "ui_sequence",      # browser automation steps
        "api_call",         # direct HTTP call
        "manual_approval",  # pause and wait for human
        "noop",             # do nothing, log only
    ]
    description: str = ""
    steps: list[ActionStep] = Field(default_factory=list)
    required_identity_score: int = 0       # minimum identity score before allowing this action
    requires_human_approval: bool = False
    verification_steps: list[ActionStep] = Field(default_factory=list)
    rollback_or_recovery_notes: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Identity field definition
# ---------------------------------------------------------------------------

class IdentityFieldDefinition(BaseModel):
    """
    One field used for identity matching.

    generic_key is the canonical name Bill Core uses internally.
    tenant_alias is the field name in the tenant's source data.
    match_type controls comparison strategy.
    weight contributes to the overall identity score (0-100).
    """
    generic_key: str                                          # "external_contact_id" | "policy_number" | "marketplace_id" | "name"
    tenant_alias: str | None = None                          # e.g. "keap_id", "ffm_id"
    match_type: Literal["exact", "fuzzy", "prefix", "numeric_exact"] = "exact"
    weight: int = Field(default=0, ge=0, le=100)             # contribution to score
    case_sensitive: bool = False
    normalize_whitespace: bool = True
    notes: str | None = None


class TenantIdentityPolicy(BaseModel):
    """
    Rules for matching a source client record to a CRM contact.

    Thresholds determine whether the worker auto-proceeds, waits for human review,
    or blocks entirely.
    """
    fields: list[IdentityFieldDefinition] = Field(default_factory=list)
    auto_proceed_score: int = Field(default=70, ge=0, le=100)
    human_review_score: int = Field(default=40, ge=0, le=100)
    block_below_score: int = Field(default=40, ge=0, le=100)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Decision rule definition
# ---------------------------------------------------------------------------

class RuleCondition(BaseModel):
    """
    One condition in a decision rule.

    field is a dot-path into the audit result context: "audit.status", "audit.agent_of_record".
    operator is the comparison to apply.
    value is the expected value.
    """
    field: str                             # e.g. "audit.status", "audit.agent_of_record"
    operator: Literal["eq", "neq", "lt", "lte", "gt", "gte", "in", "not_in", "is_null", "is_not_null"]
    value: Any = None                      # expected value; not used for is_null/is_not_null


class TenantDecisionRule(BaseModel):
    """
    A deterministic rule: if ALL conditions match, execute action_key.

    Rules are evaluated in priority order (lower number = higher priority).
    The first matching rule wins.
    """
    rule_id: str
    description: str = ""
    priority: int = 100                    # lower = evaluated first
    conditions: list[RuleCondition] = Field(default_factory=list)
    condition_logic: Literal["all", "any"] = "all"   # "all" = AND, "any" = OR
    action_key: str                        # must match an action_key in TenantActionTemplate list
    notes: str | None = None


# ---------------------------------------------------------------------------
# Safety policy
# ---------------------------------------------------------------------------

class TenantSafetyPolicy(BaseModel):
    """
    Safety guardrails applied to every run of this workflow template.

    All controls are checked before any CRM action is executed.
    """
    never_update_on_name_only: bool = True
    require_identity_score_for_crm_actions: bool = True
    dry_run_default: bool = True
    require_human_approval_for_first_n_runs: int = 50
    screenshot_before_action: bool = True
    screenshot_after_action: bool = True
    audit_log_required: bool = True
    duplicate_action_check_required: bool = True
    notes: str | None = None


# ---------------------------------------------------------------------------
# Full tenant workflow template
# ---------------------------------------------------------------------------

class TenantWorkflowTemplate(BaseModel):
    """
    Complete configuration for one tenant workflow.

    This is the root object stored in JSON files under tenant_templates/.
    Bill Core loads this at task time; all system names, selectors, identity
    fields, decision rules, and safety controls come from here.
    """
    tenant_id: str
    workflow_id: str
    workflow_name: str
    description: str = ""
    version: str = "1.0.0"
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    systems: list[TenantSystemTemplate] = Field(default_factory=list)
    actions: list[TenantActionTemplate] = Field(default_factory=list)
    identity_policy: TenantIdentityPolicy = Field(default_factory=TenantIdentityPolicy)
    decision_rules: list[TenantDecisionRule] = Field(default_factory=list)
    safety_policy: TenantSafetyPolicy = Field(default_factory=TenantSafetyPolicy)

    # Freeform metadata for UI display / future use
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# API request / response helpers
# ---------------------------------------------------------------------------

class TemplateListItem(BaseModel):
    tenant_id: str
    workflow_id: str
    workflow_name: str
    version: str
    enabled: bool
    tags: list[str]
    description: str


class TemplateValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IdentityScoreRequest(BaseModel):
    """Test payload for the identity scoring endpoint."""
    source_record: dict[str, Any]         # field_key -> value from source system
    target_contact: dict[str, Any]        # field_key -> value from CRM
    use_aliases: bool = True              # resolve tenant_alias -> generic_key before scoring


class IdentityScoreResult(BaseModel):
    score: int
    max_possible_score: int
    field_results: list[dict[str, Any]] = Field(default_factory=list)
    verdict: Literal["auto_proceed", "human_review", "block"]
    notes: str = ""


class DecisionTestRequest(BaseModel):
    """Test payload for the decision rule evaluation endpoint."""
    audit_context: dict[str, Any]         # e.g. {"audit": {"status": "past_due", "agent_of_record": True}}


class DecisionTestResult(BaseModel):
    matched_rule_id: str | None = None
    action_key: str | None = None
    description: str = ""
    evaluated_rules: list[dict[str, Any]] = Field(default_factory=list)
