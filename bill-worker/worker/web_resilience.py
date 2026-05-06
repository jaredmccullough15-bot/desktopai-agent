from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
import re

from playwright.sync_api import BrowserContext, Page


@dataclass
class PageState:
    url: str
    title: str
    visible_text_sample: str
    detected_modals: list[str] = field(default_factory=list)
    detected_overlays: list[str] = field(default_factory=list)
    important_buttons: list[str] = field(default_factory=list)
    important_inputs: list[str] = field(default_factory=list)
    open_tab_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SafeClickResult:
    clicked: bool
    method: str
    target: str
    confidence: str
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WebResilience:
    """Small, reusable page resilience helpers for Playwright workers."""

    @staticmethod
    def _redact_sensitive_text(value: str, max_len: int = 300) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        # Redact common sensitive patterns before truncation.
        text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[redacted_email]", text)
        text = re.sub(r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b", "[redacted_ssn]", text)
        text = re.sub(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[redacted_phone]", text)

        if len(text) > max_len:
            return text[:max_len]
        return text

    def snapshot_for_failure(self, page: Page, failed_action: str, attempted_fallbacks: list[str] | None = None) -> dict[str, Any]:
        state = self.capture_page_state(page).to_dict()
        return {
            "page_state_snapshot": {
                **state,
                "visible_text_sample": self._redact_sensitive_text(str(state.get("visible_text_sample") or ""), max_len=300),
            },
            "detected_modals": [str(item) for item in (state.get("detected_modals") or [])][:8],
            "detected_overlays": [str(item) for item in (state.get("detected_overlays") or [])][:8],
            "failed_action": str(failed_action or ""),
            "attempted_fallbacks": [str(item) for item in (attempted_fallbacks or [])][:20],
            "captured_at": datetime.utcnow().isoformat(),
        }

    def capture_page_state(self, page: Page) -> PageState:
        url = str(page.url or "")
        title = ""
        visible_text_sample = ""
        detected_modals: list[str] = []
        detected_overlays: list[str] = []
        important_buttons: list[str] = []
        important_inputs: list[str] = []
        open_tab_count = 0

        try:
            title = str(page.title() or "")
        except Exception:
            title = ""

        try:
            tab_count = len(page.context.pages)
            open_tab_count = int(tab_count)
        except Exception:
            open_tab_count = 0

        try:
            state = page.evaluate(
                r"""
                () => {
                    const clip = (value, maxLen = 320) => {
                        const text = String(value || '').replace(/\s+/g, ' ').trim();
                        return text.length > maxLen ? text.slice(0, maxLen) : text;
                    };

                    const sampleText = clip((document.body && (document.body.innerText || document.body.textContent)) || '', 800);

                    const modalSelectors = [
                        '[role="dialog"]',
                        '[role="alertdialog"]',
                        '.MuiDialog-root',
                        '.MuiModal-root',
                    ];
                    const overlaySelectors = [
                        '.MuiBackdrop-root',
                        '.MuiModal-backdrop',
                        '[class*="overlay" i]',
                        '[class*="backdrop" i]',
                    ];

                    const findVisible = (selectors) => {
                        const found = [];
                        for (const selector of selectors) {
                            const nodes = Array.from(document.querySelectorAll(selector));
                            for (const node of nodes) {
                                const style = window.getComputedStyle(node);
                                if (style.display === 'none' || style.visibility === 'hidden') continue;
                                const text = clip(node.innerText || node.textContent || '', 120);
                                found.push(text ? `${selector}:${text}` : selector);
                                if (found.length >= 6) return found;
                            }
                        }
                        return found;
                    };

                    const buttonTexts = Array.from(document.querySelectorAll('button, [role="button"], a'))
                        .map((el) => clip(el.innerText || el.textContent || '', 60))
                        .filter(Boolean)
                        .slice(0, 8);

                    const inputHints = Array.from(document.querySelectorAll('input, textarea, select'))
                        .map((el) => clip(el.getAttribute('name') || el.getAttribute('placeholder') || el.id || '', 80))
                        .filter(Boolean)
                        .slice(0, 8);

                    return {
                        visible_text_sample: sampleText,
                        detected_modals: findVisible(modalSelectors),
                        detected_overlays: findVisible(overlaySelectors),
                        important_buttons: buttonTexts,
                        important_inputs: inputHints,
                    };
                }
                """
            )
            if isinstance(state, dict):
                visible_text_sample = self._redact_sensitive_text(str(state.get("visible_text_sample") or ""), max_len=300)
                detected_modals = [str(item) for item in (state.get("detected_modals") or [])]
                detected_overlays = [str(item) for item in (state.get("detected_overlays") or [])]
                important_buttons = [str(item) for item in (state.get("important_buttons") or [])]
                important_inputs = [str(item) for item in (state.get("important_inputs") or [])]
        except Exception:
            pass

        return PageState(
            url=url,
            title=title,
            visible_text_sample=visible_text_sample,
            detected_modals=detected_modals,
            detected_overlays=detected_overlays,
            important_buttons=important_buttons,
            important_inputs=important_inputs,
            open_tab_count=open_tab_count,
        )

    def detect_modal(self, page: Page) -> bool:
        try:
            value = page.evaluate(
                """
                () => {
                    const selectors = ['[role="dialog"]', '[role="alertdialog"]', '.MuiDialog-root', '.MuiModal-root'];
                    for (const selector of selectors) {
                        for (const el of document.querySelectorAll(selector)) {
                            if (el.getAttribute('aria-hidden') === 'true') continue;
                            const s = window.getComputedStyle(el);
                            if (s.display === 'none' || s.visibility === 'hidden') continue;
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            return bool(value)
        except Exception:
            return False

    def detect_overlay(self, page: Page) -> bool:
        try:
            value = page.evaluate(
                """
                () => {
                    const selectors = ['.MuiBackdrop-root', '.MuiModal-backdrop', '[class*="overlay" i]', '[class*="backdrop" i]'];
                    for (const selector of selectors) {
                        for (const el of document.querySelectorAll(selector)) {
                            const s = window.getComputedStyle(el);
                            if (s.display === 'none' || s.visibility === 'hidden') continue;
                            if (parseFloat(s.opacity || '1') < 0.01) continue;
                            if (s.pointerEvents === 'none') continue;
                            return true;
                        }
                    }
                    return false;
                }
                """
            )
            return bool(value)
        except Exception:
            return False

    def find_clickable(self, page: Page, labels: list[str]) -> Any | None:
        for label in labels:
            label_value = str(label or "").strip()
            if not label_value:
                continue
            candidates = [
                f"button:has-text('{label_value}')",
                f"a:has-text('{label_value}')",
                f"[role='button']:has-text('{label_value}')",
                f"text={label_value}",
            ]
            for selector in candidates:
                try:
                    node = page.locator(selector).first
                    if node.count() > 0 and node.is_visible():
                        return node
                except Exception:
                    continue
        return None

    def safe_click(self, page: Page, labels: list[str], selectors: list[str]) -> SafeClickResult:
        # Strict deterministic order: selectors first, then label-based discovery.
        for selector in selectors:
            candidate = str(selector or "").strip()
            if not candidate:
                continue
            try:
                node = page.locator(candidate).first
                if node.count() == 0 or not node.is_visible():
                    continue
                node.click()
                return SafeClickResult(
                    clicked=True,
                    method="selector",
                    target=candidate,
                    confidence="high",
                )
            except Exception:
                continue

        node = self.find_clickable(page, labels)
        if node is not None:
            try:
                node.click()
                return SafeClickResult(
                    clicked=True,
                    method="label",
                    target="label-based",
                    confidence="medium",
                )
            except Exception as exc:
                return SafeClickResult(
                    clicked=False,
                    method="label",
                    target="label-based",
                    confidence="low",
                    details=f"label click failed: {exc}",
                )

        return SafeClickResult(
            clicked=False,
            method="none",
            target="",
            confidence="low",
            details="no selector or label candidate was clickable",
        )

    def dismiss_known_modals(self, page: Page) -> bool:
        selectors = [
            "button[aria-label*='close' i]",
            "[role='dialog'] button:has-text('Close')",
            "[role='dialog'] button:has-text('Cancel')",
            "button:has-text('Dismiss')",
            "button:has-text('No thanks')",
            ".MuiDialog-root button:has-text('Close')",
            ".MuiDialog-root button:has-text('Cancel')",
        ]

        for selector in selectors:
            try:
                node = page.locator(selector).first
                if node.count() > 0 and node.is_visible():
                    node.click(timeout=1500)
                    return True
            except Exception:
                continue

        try:
            page.keyboard.press("Escape")
            return not (self.detect_modal(page) or self.detect_overlay(page))
        except Exception:
            return False

    def ensure_expected_page(self, page: Page, expected_url_contains: str, expected_text: str) -> bool:
        current_url = str(page.url or "").lower()
        url_ok = expected_url_contains.lower() in current_url if expected_url_contains else True
        if not url_ok:
            return False
        if not expected_text:
            return True
        try:
            return page.get_by_text(expected_text, exact=False).first.is_visible(timeout=1200)
        except Exception:
            return False

    def cleanup_extra_tabs(self, context: BrowserContext, keep_page: Page) -> int:
        closed = 0
        for page in list(context.pages):
            if page is keep_page:
                continue
            try:
                page.close()
                closed += 1
            except Exception:
                continue
        try:
            keep_page.bring_to_front()
        except Exception:
            pass
        return closed
