"""
Teaching Co-Pilot Service — Phase 1
Converts low-level browser events into human-readable summaries, applies smart
interruption rules, resolves natural references, and determines live-command
handling strategy (observe vs. execute).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Sensitive field detection
# ---------------------------------------------------------------------------
_SENSITIVE_PATTERNS = re.compile(
    r"(password|passwd|mfa|otp|pin\b|ssn|social.?security|token|secret|auth.?code|"
    r"dob|date.?of.?birth|phone|email|credit.?card|cvv|card.?number)",
    re.IGNORECASE,
)

_MAX_BUTTONS = 20
_MAX_INPUTS = 20
_MAX_LINKS = 20
_MAX_HEADINGS = 10
_MAX_TEXT = 120


def _is_sensitive(label: str) -> bool:
    return bool(_SENSITIVE_PATTERNS.search(label or ""))


def _clean_text(value: Any, max_len: int = _MAX_TEXT) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


# ---------------------------------------------------------------------------
# Page Context Snapshot
# ---------------------------------------------------------------------------
@dataclass
class PageContextSnapshot:
    url: str = ""
    title: str = ""
    visible_buttons: list[dict] = field(default_factory=list)   # {text, aria_label, role, selector_hint}
    visible_inputs: list[dict] = field(default_factory=list)    # {label, placeholder, type, name, selector_hint, sensitive}
    visible_links: list[dict] = field(default_factory=list)     # {text, href}
    visible_headings: list[dict] = field(default_factory=list)  # {text, level}
    # Backward-compatible aliases used in existing logic/UI
    buttons: list[str] = field(default_factory=list)
    inputs: list[dict] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    active_element: dict | None = None                       # {type, label}
    recent_click_label: str | None = None
    recent_type_field: str | None = None
    recent_clicked_element: dict | None = None
    recent_typed_field: str | None = None
    modal_present: bool = False
    modal_title: str | None = None
    modal_summary: dict | None = None
    page_changed: bool = False
    captured_at: float = field(default_factory=time.time)

    @classmethod
    def from_raw(cls, raw: dict) -> "PageContextSnapshot":
        """Build from a dict posted by the browser extension / worker."""
        buttons_raw = raw.get("visible_buttons")
        if not buttons_raw:
            buttons_raw = [{"text": b, "aria_label": "", "role": "button", "selector_hint": None} for b in (raw.get("buttons") or [])]
        safe_buttons: list[dict] = []
        for btn in list(buttons_raw)[:_MAX_BUTTONS]:
            text = _clean_text((btn or {}).get("text") or (btn or {}).get("label") or "")
            aria_label = _clean_text((btn or {}).get("aria_label") or "")
            role = _clean_text((btn or {}).get("role") or "button")
            selector_hint = _clean_text((btn or {}).get("selector_hint") or "") or None
            safe_buttons.append(
                {
                    "text": text,
                    "aria_label": aria_label,
                    "role": role,
                    "selector_hint": selector_hint,
                }
            )

        inputs_raw = raw.get("visible_inputs")
        if not inputs_raw:
            inputs_raw = raw.get("inputs") or []
        safe_inputs: list[dict] = []
        for inp in list(inputs_raw)[:_MAX_INPUTS]:
            label = _clean_text((inp or {}).get("label") or "")
            placeholder = _clean_text((inp or {}).get("placeholder") or "")
            input_type = _clean_text((inp or {}).get("type") or "text")
            name = _clean_text((inp or {}).get("name") or "")
            selector_hint = _clean_text((inp or {}).get("selector_hint") or "") or None
            explicit_sensitive = bool((inp or {}).get("sensitive"))
            sensitive = explicit_sensitive or _is_sensitive(f"{label} {placeholder} {name} {input_type}")
            if sensitive:
                safe_inputs.append(
                    {
                        "label": "[redacted]",
                        "placeholder": "[redacted]",
                        "type": input_type,
                        "name": "[redacted]",
                        "selector_hint": None,
                        "sensitive": True,
                    }
                )
            else:
                safe_inputs.append(
                    {
                        "label": label,
                        "placeholder": placeholder,
                        "type": input_type,
                        "name": name,
                        "selector_hint": selector_hint,
                        "sensitive": False,
                    }
                )

        links_raw = raw.get("visible_links")
        if not links_raw:
            links_raw = [{"text": l, "href": ""} for l in (raw.get("links") or [])]
        safe_links: list[dict] = []
        for link in list(links_raw)[:_MAX_LINKS]:
            text = _clean_text((link or {}).get("text") or "")
            href = _clean_text((link or {}).get("href") or "")
            safe_links.append({"text": text, "href": href})

        headings_raw = raw.get("visible_headings")
        if not headings_raw:
            headings_raw = [{"text": h, "level": None} for h in (raw.get("headings") or [])]
        safe_headings: list[dict] = []
        for heading in list(headings_raw)[:_MAX_HEADINGS]:
            text = _clean_text((heading or {}).get("text") or "")
            level = (heading or {}).get("level")
            if _is_sensitive(text):
                text = "[redacted]"
            safe_headings.append({"text": text, "level": level})

        active = raw.get("active_element")
        if active:
            active = {
                "type": _clean_text((active or {}).get("type") or ""),
                "label": _clean_text((active or {}).get("label") or ""),
            }
            if _is_sensitive(active.get("label", "")):
                active["label"] = "[redacted]"

        recent_clicked_element = raw.get("recent_clicked_element")
        if recent_clicked_element:
            recent_clicked_element = {
                "text": _clean_text((recent_clicked_element or {}).get("text") or (recent_clicked_element or {}).get("label") or ""),
                "role": _clean_text((recent_clicked_element or {}).get("role") or ""),
            }
            if _is_sensitive(recent_clicked_element.get("text", "")):
                recent_clicked_element["text"] = "[redacted]"

        recent_click = _clean_text(raw.get("recent_click_label") or (recent_clicked_element or {}).get("text") or "") or None
        recent_type = _clean_text(raw.get("recent_type_field") or raw.get("recent_typed_field") or "") or None
        if recent_type and _is_sensitive(recent_type):
            recent_type = "[redacted]"

        modal_summary = raw.get("modal_summary")
        if modal_summary:
            modal_summary = {
                "present": bool((modal_summary or {}).get("present", True)),
                "title": _clean_text((modal_summary or {}).get("title") or ""),
                "text": _clean_text((modal_summary or {}).get("text") or ""),
            }
            if _is_sensitive(str(modal_summary.get("title") or "")):
                modal_summary["title"] = "[redacted]"
            if _is_sensitive(str(modal_summary.get("text") or "")):
                modal_summary["text"] = "[redacted]"

        modal_present = bool(raw.get("modal_present"))
        if modal_summary:
            modal_present = bool(modal_summary.get("present", modal_present))

        modal_title = _clean_text(raw.get("modal_title") or (modal_summary or {}).get("title") or "") or None
        return cls(
            url=_clean_text(raw.get("url") or ""),
            title=_clean_text(raw.get("title") or ""),
            visible_buttons=safe_buttons,
            visible_inputs=safe_inputs,
            visible_links=safe_links,
            visible_headings=safe_headings,
            buttons=[b.get("text") or "" for b in safe_buttons if b.get("text")],
            inputs=[{"label": i.get("label"), "placeholder": i.get("placeholder"), "type": i.get("type")} for i in safe_inputs],
            links=[l.get("text") or "" for l in safe_links if l.get("text")],
            headings=[h.get("text") or "" for h in safe_headings if h.get("text")],
            active_element=active,
            recent_click_label=recent_click,
            recent_type_field=recent_type,
            recent_clicked_element=recent_clicked_element,
            recent_typed_field=recent_type,
            modal_present=modal_present,
            modal_title=modal_title,
            modal_summary=modal_summary,
            page_changed=bool(raw.get("page_changed")),
            captured_at=float(raw.get("captured_at") or time.time()),
        )

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "visible_buttons": self.visible_buttons,
            "visible_inputs": self.visible_inputs,
            "visible_links": self.visible_links,
            "visible_headings": self.visible_headings,
            "buttons": self.buttons,
            "inputs": self.inputs,
            "links": self.links,
            "headings": self.headings,
            "active_element": self.active_element,
            "recent_click_label": self.recent_click_label,
            "recent_type_field": self.recent_type_field,
            "recent_clicked_element": self.recent_clicked_element,
            "recent_typed_field": self.recent_typed_field,
            "modal_present": self.modal_present,
            "modal_title": self.modal_title,
            "modal_summary": self.modal_summary,
            "page_changed": self.page_changed,
            "captured_at": self.captured_at,
        }


# ---------------------------------------------------------------------------
# Action Interpreter (Part 2)
# ---------------------------------------------------------------------------
_LOGIN_LABELS = re.compile(
    r"\b(sign.?in|log.?in|login|log in|sign in|submit|continue|next|proceed)\b",
    re.IGNORECASE,
)
_SEARCH_LABELS = re.compile(r"\b(search|find|lookup|look up|go)\b", re.IGNORECASE)
_UPLOAD_LABELS = re.compile(r"\b(upload|attach|choose file|browse)\b", re.IGNORECASE)
_DOWNLOAD_LABELS = re.compile(r"\b(download|export|save file|save as)\b", re.IGNORECASE)
_SUBMIT_LABELS = re.compile(r"\b(submit|save|confirm|apply|done|finish)\b", re.IGNORECASE)


@dataclass
class ActionInterpretation:
    noticed: str          # "I saw you …"
    interpretation: str   # "I think this …"
    question: str | None  # "Bill's question" — None if not warranted
    confidence: float     # 0.0-1.0
    should_interrupt: bool


def interpret_action(
    action: dict,
    page_context: PageContextSnapshot | None = None,
) -> ActionInterpretation:
    """Convert a low-level browser event dict into a human Co-Pilot message."""
    action_type = (action.get("type") or "").lower()
    label = (action.get("label") or "").strip()
    url = (action.get("url") or (page_context.url if page_context else "")).strip()
    field_label = (action.get("field_label") or label or "").strip()

    if _is_sensitive(label) or _is_sensitive(field_label):
        label = "[sensitive field]"
        field_label = "[sensitive field]"

    if action_type == "navigate":
        path = _url_path(url)
        noticed = f"I saw you open {path or 'a new page'}."
        interpretation = _interpret_navigation(url, page_context)
        question = None
        confidence = 0.85
        should_interrupt = True

    elif action_type == "click":
        display = label or "an element"
        noticed = f"I saw you click {display}."
        is_login = bool(_LOGIN_LABELS.search(label))
        is_search = bool(_SEARCH_LABELS.search(label))
        if is_login:
            interpretation = f"I think clicking {display} submits the login form."
            question = f"Is clicking {display} always required, or only when not already logged in?"
            confidence = 0.80
            should_interrupt = True
        elif is_search:
            interpretation = f"I think {display} starts a search."
            question = f"What should Bill search for here — a fixed value or something from the task?"
            confidence = 0.75
            should_interrupt = True
        elif _UPLOAD_LABELS.search(label):
            interpretation = f"I think clicking {display} triggers a file upload."
            question = "What file should Bill upload here?"
            confidence = 0.70
            should_interrupt = True
        elif _DOWNLOAD_LABELS.search(label):
            interpretation = f"I think clicking {display} downloads or exports data."
            question = None
            confidence = 0.80
            should_interrupt = False
        else:
            interpretation = f"I noted the click on {display}."
            question = None
            confidence = 0.60
            should_interrupt = False

    elif action_type == "type":
        safe_field = field_label if not _is_sensitive(field_label) else "[sensitive field]"
        noticed = f"I saw you fill in the {safe_field} field."
        interpretation = (
            f"I'll treat the {safe_field} field as a required input, "
            "but I won't store the value."
        )
        question = None
        confidence = 0.85
        should_interrupt = False

    elif action_type == "submit":
        form_name = label or "a form"
        noticed = f"I saw you submit {form_name}."
        interpretation = f"I think this step submits the form."
        question = f"What should Bill check before submitting?"
        confidence = 0.75
        should_interrupt = True

    elif action_type == "select":
        display = label or "a dropdown"
        noticed = f"I saw you select an option in {display}."
        interpretation = f"I noted the selection in {display}."
        question = "Is this selection always the same, or does it vary per task?"
        confidence = 0.65
        should_interrupt = False

    else:
        noticed = f"I noticed a browser action ({action_type})."
        interpretation = "I'm not sure what this step means yet."
        question = "Can you explain what just happened?"
        confidence = 0.30
        should_interrupt = True

    return ActionInterpretation(
        noticed=noticed,
        interpretation=interpretation,
        question=question,
        confidence=confidence,
        should_interrupt=should_interrupt,
    )


def _url_path(url: str) -> str:
    try:
        from urllib.parse import urlparse
        p = urlparse(url)
        path = p.path.rstrip("/")
        return path or p.netloc or url
    except Exception:
        return url


def _interpret_navigation(url: str, ctx: PageContextSnapshot | None) -> str:
    path = _url_path(url).lower()
    if any(k in path for k in ("login", "signin", "sign-in", "auth")):
        return "I saw you open the sign-in page."
    if any(k in path for k in ("dashboard", "home", "overview")):
        return "I saw you navigate to the main dashboard."
    if any(k in path for k in ("search", "find")):
        return "I saw you open a search page."
    title = (ctx.title if ctx else "") or ""
    if title:
        return f"I saw you navigate to '{title}'."
    return f"I saw you navigate to a new page."


# ---------------------------------------------------------------------------
# Smart Interruption Rules (Part 3)
# ---------------------------------------------------------------------------
_INTERRUPT_COOLDOWN_SECONDS = 8.0  # minimum gap between Bill asking questions


class InterruptionTracker:
    """Per-session cooldown tracker."""

    def __init__(self) -> None:
        self._last_interrupt_at: float = 0.0
        self._question_count: int = 0

    def should_interrupt(
        self,
        action: dict,
        interpretation: ActionInterpretation,
        page_context: PageContextSnapshot | None = None,
    ) -> bool:
        """Return True only if this action warrants asking the employee a question."""
        now = time.time()
        action_type = (action.get("type") or "").lower()
        label = (action.get("label") or "").lower()

        # Always interrupt on page change, form submit, modal
        force = (
            action_type == "navigate"
            or action_type == "submit"
            or (page_context and page_context.modal_present)
        )

        # Interrupt on high-signal clicks
        high_signal_click = action_type == "click" and bool(_LOGIN_LABELS.search(label) or _SEARCH_LABELS.search(label) or _UPLOAD_LABELS.search(label))

        # Interrupt when Bill is unsure
        low_confidence = interpretation.confidence < 0.50

        wants_to_interrupt = (
            force
            or high_signal_click
            or low_confidence
            or interpretation.should_interrupt
        )

        if not wants_to_interrupt:
            return False

        # Apply cooldown
        if now - self._last_interrupt_at < _INTERRUPT_COOLDOWN_SECONDS:
            return False

        self._last_interrupt_at = now
        self._question_count += 1
        return True

    def reset(self) -> None:
        self._last_interrupt_at = 0.0
        self._question_count = 0


# ---------------------------------------------------------------------------
# Natural Reference Resolution (Part 4)
# ---------------------------------------------------------------------------
_REFERENCE_PATTERNS = [
    (re.compile(r"\b(that button|this button|click that|click it)\b", re.IGNORECASE), "button"),
    (re.compile(r"\b(that field|this field|that input|this input|that box|this box|use that field|use this field|search box)\b", re.IGNORECASE), "input"),
    (re.compile(r"\b(that link|this link)\b", re.IGNORECASE), "link"),
    (re.compile(r"\b(that popup|that modal|this popup|the popup|that dialog)\b", re.IGNORECASE), "modal"),
    (re.compile(r"\b(the login button|login button)\b", re.IGNORECASE), "button"),
    (re.compile(r"\b(this step|that step)\b", re.IGNORECASE), "step"),
]


@dataclass
class ReferenceResolution:
    resolved: str | None        # human label of what was resolved, e.g. "Sign In button"
    selector: str | None        # CSS/xpath selector if known
    clarification_needed: bool  # True if Bill should ask
    clarification_prompt: str | None  # What Bill should ask


def resolve_natural_reference(
    text: str,
    page_context: PageContextSnapshot | None,
    recent_action: dict | None = None,
) -> ReferenceResolution:
    """
    Try to resolve vague references like 'that button', 'this field', 'that popup'
    using the current page context and most recent observed action.
    """
    text_lower = text.lower()
    ref_type = None
    for pattern, rtype in _REFERENCE_PATTERNS:
        if pattern.search(text_lower):
            ref_type = rtype
            break

    if ref_type is None:
        return ReferenceResolution(resolved=None, selector=None, clarification_needed=False, clarification_prompt=None)

    if ref_type == "modal" and page_context and page_context.modal_present:
        label = page_context.modal_title or "current modal/dialog"
        return ReferenceResolution(resolved=label, selector=None, clarification_needed=False, clarification_prompt=None)

    if ref_type == "button":
        # Use recent click or most prominent button
        if recent_action and recent_action.get("type") == "click":
            lbl = recent_action.get("label") or ""
            if lbl and not _is_sensitive(lbl):
                return ReferenceResolution(resolved=f"{lbl} button", selector=recent_action.get("selector"), clarification_needed=False, clarification_prompt=None)
        if page_context and page_context.recent_click_label:
            return ReferenceResolution(resolved=f"{page_context.recent_click_label} button", selector=None, clarification_needed=False, clarification_prompt=None)
        button_labels = list(page_context.buttons if page_context else [])
        if page_context and page_context.visible_buttons:
            button_labels = [b.get("text") or "" for b in page_context.visible_buttons if b.get("text")]
        link_labels: list[str] = []
        if page_context:
            if page_context.visible_links:
                link_labels = [l.get("text") or "" for l in page_context.visible_links if l.get("text")]
            elif page_context.links:
                link_labels = [l for l in page_context.links if l]

        if button_labels:
            if "login button" in text_lower:
                for btn in button_labels:
                    if _LOGIN_LABELS.search(btn or ""):
                        return ReferenceResolution(resolved=f"{btn} button", selector=None, clarification_needed=False, clarification_prompt=None)
            if len(button_labels) == 1 and link_labels:
                return ReferenceResolution(
                    resolved=None,
                    selector=None,
                    clarification_needed=True,
                    clarification_prompt=f"Do you mean the {button_labels[0]} button or the {link_labels[0]} link?",
                )
            if len(button_labels) == 1:
                return ReferenceResolution(resolved=f"{button_labels[0]} button", selector=None, clarification_needed=False, clarification_prompt=None)
            candidates = ", ".join(f'"{b}"' for b in button_labels[:4])
            return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt=f"Which button do you mean? I can see: {candidates}.")
        return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt="Which button do you mean? I don't have visibility into the page yet.")

    if ref_type == "input":
        if recent_action and recent_action.get("type") == "type":
            fl = recent_action.get("field_label") or recent_action.get("label") or ""
            if fl and not _is_sensitive(fl):
                return ReferenceResolution(resolved=f"{fl} field", selector=recent_action.get("selector"), clarification_needed=False, clarification_prompt=None)
        if page_context and page_context.recent_type_field:
            return ReferenceResolution(resolved=f"{page_context.recent_type_field} field", selector=None, clarification_needed=False, clarification_prompt=None)
        if page_context and page_context.active_element and page_context.active_element.get("type") in ("input", "textarea"):
            lbl = page_context.active_element.get("label") or ""
            if lbl and not _is_sensitive(lbl):
                return ReferenceResolution(resolved=f"{lbl} field", selector=None, clarification_needed=False, clarification_prompt=None)
        input_rows = page_context.inputs if page_context else []
        if page_context and page_context.visible_inputs:
            input_rows = page_context.visible_inputs
        if input_rows:
            if len(input_rows) == 1:
                lbl = input_rows[0].get("label") or input_rows[0].get("placeholder") or "input"
                return ReferenceResolution(resolved=f"{lbl} field", selector=None, clarification_needed=False, clarification_prompt=None)
            candidates = ", ".join(f'"{i.get("label") or i.get("placeholder", "field")}"' for i in input_rows[:4])
            return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt=f"Which field do you mean? I can see: {candidates}.")
        return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt="Which field do you mean?")

    if ref_type == "link":
        links = page_context.links if page_context else []
        if page_context and page_context.visible_links:
            links = [l.get("text") or "" for l in page_context.visible_links if l.get("text")]
        if links:
            if len(links) == 1:
                return ReferenceResolution(resolved=links[0], selector=None, clarification_needed=False, clarification_prompt=None)
            candidates = ", ".join(f'"{l}"' for l in links[:4])
            return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt=f"Which link do you mean? I can see: {candidates}.")
        return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt="Which link do you mean?")

    return ReferenceResolution(resolved=None, selector=None, clarification_needed=True, clarification_prompt="I'm not sure what you're referring to. Can you describe it?")


# ---------------------------------------------------------------------------
# Live Command Clarity (Part 5)
# ---------------------------------------------------------------------------
# Teaching Mode is observation-only: the co-pilot never live-clicks autonomously.
# Strategy A: future live-click capable (not yet implemented)
# Strategy B: observation-only — Bill asks employee to perform the action
# Strategy C: if selector known from page context — create executable step immediately

LIVE_CLICK_SUPPORTED = False  # flip to True when worker gains live-click capability


@dataclass
class LiveCommandDecision:
    strategy: str           # "observe" | "execute" | "step_created"
    reply: str              # What Bill says aloud/in chat
    step_created: bool      # True if an executable step was produced
    step_label: str | None  # Label for the created step
    selector: str | None    # Selector for the step, if known


def handle_live_command(
    command_text: str,
    page_context: PageContextSnapshot | None = None,
    recent_action: dict | None = None,
) -> LiveCommandDecision:
    """
    Determine how to respond to an employee command like 'Click Sign In'.

    Returns strategy A (execute), B (observe), or C (step_created from context).
    """
    # Extract intent label from command
    click_match = re.search(
        r"\b(?:click|tap|press|hit|select)\s+(?:the\s+)?(.+?)(?:\s+button|\s+link|\s+icon)?$",
        command_text.strip(),
        re.IGNORECASE,
    )
    raw_label = click_match.group(1).strip() if click_match else command_text.strip()
    # Strip technical selector hints from human-facing phrasing.
    raw_label = re.sub(r"\bselector\s*:\s*.+$", "", raw_label, flags=re.IGNORECASE).strip()
    raw_label = re.sub(r"[#\.][A-Za-z0-9_-]+", "", raw_label).strip()
    raw_label = re.sub(r"\s+", " ", raw_label).strip(" .")
    if not raw_label:
        raw_label = "target control"
    display_label = raw_label

    # Try to resolve via page context
    resolved_selector: str | None = None
    if page_context:
        # Look for exact/partial match in known buttons
        button_labels = page_context.buttons
        if page_context.visible_buttons:
            button_labels = [b.get("text") or "" for b in page_context.visible_buttons if b.get("text")]
        for btn in button_labels:
            if raw_label.lower() in btn.lower() or btn.lower() in raw_label.lower():
                display_label = btn
                break
        # Check recent action for selector
        if recent_action and recent_action.get("type") == "click":
            if recent_action.get("label", "").lower() == raw_label.lower():
                resolved_selector = recent_action.get("selector")

    if LIVE_CLICK_SUPPORTED:
        # Strategy A: execute live
        return LiveCommandDecision(
            strategy="execute",
            reply=f"Bill clicked {display_label}.",
            step_created=True,
            step_label=f"Click {display_label}",
            selector=resolved_selector,
        )

    if resolved_selector:
        # Strategy C: selector known — create executable step immediately
        return LiveCommandDecision(
            strategy="step_created",
            reply=f"Got it. I've recorded a click on {display_label} as an executable step.",
            step_created=True,
            step_label=f"Click {display_label}",
            selector=resolved_selector,
        )

    # Strategy B: ask employee to perform the action while Bill watches
    return LiveCommandDecision(
        strategy="observe",
        reply=f"Go ahead and click {display_label} now. I'll watch and record it.",
        step_created=False,
        step_label=None,
        selector=None,
    )
