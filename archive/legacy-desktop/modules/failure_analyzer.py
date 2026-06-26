import os
import re
import time
from typing import Any


class FailureAnalyzer:
    FAILURE_CLASSES = {
        "element_not_found": "element not found",
        "element_not_clickable": "element not clickable",
        "page_loading": "page still loading",
        "wrong_frame": "wrong frame",
        "modal_blocking": "popup/modal blocking",
        "stale_selector": "stale selector",
        "auth_expired": "auth/session expired",
        "download_issue": "download dialog issue",
    }

    RECOVERY_MAP = {
        "element_not_found": [
            "retry_longer_wait",
            "requery_locator",
            "try_alternate_selector",
            "check_iframe",
            "check_modal",
        ],
        "element_not_clickable": [
            "scroll_into_view",
            "requery_locator",
            "check_modal",
            "check_new_tab",
        ],
        "page_loading": ["retry_longer_wait", "reopen_or_back"],
        "wrong_frame": ["check_iframe", "requery_locator"],
        "modal_blocking": ["check_modal", "retry_longer_wait"],
        "stale_selector": ["requery_locator", "try_alternate_selector"],
        "auth_expired": ["re_authenticate", "reopen_or_back"],
        "download_issue": ["check_new_tab", "handle_download"],
    }

    def __init__(self, screenshot_dir: str = os.path.join("data", "screenshots")) -> None:
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def analyze(
        self,
        page,
        error: Exception | str,
        target_hint: str = "",
        console_errors: list[str] | None = None,
    ) -> dict[str, Any]:
        error_text = str(error or "")
        now = int(time.time())
        shot_path = os.path.join(self.screenshot_dir, f"failure_{now}.png")

        url = ""
        title = ""
        visible_controls: list[dict[str, str]] = []
        dom_excerpt = ""
        loading_state = ""

        try:
            url = page.url or ""
        except Exception:
            pass

        try:
            title = page.title() or ""
        except Exception:
            pass

        try:
            page.screenshot(path=shot_path, full_page=True)
        except Exception:
            shot_path = ""

        try:
            loading_state = page.evaluate("document.readyState")
        except Exception:
            loading_state = ""

        try:
            visible_controls = page.evaluate(
                """
                () => {
                  const nodes = Array.from(document.querySelectorAll('button,a,input,select,textarea,[role]'));
                  const visible = nodes.filter(n => {
                    const r = n.getBoundingClientRect();
                    const style = window.getComputedStyle(n);
                    return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                  }).slice(0, 80);
                  return visible.map(n => ({
                    tag: (n.tagName || '').toLowerCase(),
                    text: (n.innerText || n.value || '').trim().slice(0, 120),
                    role: (n.getAttribute('role') || '').trim(),
                    name: (n.getAttribute('name') || '').trim(),
                    placeholder: (n.getAttribute('placeholder') || '').trim(),
                    ariaLabel: (n.getAttribute('aria-label') || '').trim(),
                  }));
                }
                """
            )
        except Exception:
            visible_controls = []

        if target_hint:
            try:
                dom_excerpt = page.evaluate(
                    """
                    (hint) => {
                      const q = String(hint || '').toLowerCase();
                      const all = Array.from(document.querySelectorAll('*')).slice(0, 5000);
                      for (const el of all) {
                        const text = ((el.innerText || el.textContent || '') + ' ' + (el.getAttribute?.('aria-label') || '')).toLowerCase();
                        if (q && text.includes(q)) {
                          return (el.outerHTML || '').slice(0, 1200);
                        }
                      }
                      return '';
                    }
                    """,
                    target_hint,
                )
            except Exception:
                dom_excerpt = ""

        failure_class = self._classify(error_text, loading_state, url, title, console_errors or [])
        recovery = self.RECOVERY_MAP.get(failure_class, ["retry_longer_wait", "try_alternate_selector"])

        return {
            "failure_class": failure_class,
            "failure_label": self.FAILURE_CLASSES.get(failure_class, failure_class),
            "error": error_text,
            "screenshot": shot_path,
            "url": url,
            "title": title,
            "visible_controls": visible_controls,
            "dom_excerpt": dom_excerpt,
            "console_errors": console_errors or [],
            "loading_state": loading_state,
            "recovery_strategies": recovery,
        }

    def _classify(
        self,
        error_text: str,
        loading_state: str,
        url: str,
        title: str,
        console_errors: list[str],
    ) -> str:
        e = (error_text or "").lower()
        u = (url or "").lower()
        t = (title or "").lower()
        logs = " ".join(console_errors).lower()

        if any(k in e for k in ["not found", "no node", "unable to locate", "timeout"]):
            if loading_state and loading_state != "complete":
                return "page_loading"
            return "element_not_found"
        if any(k in e for k in ["not clickable", "intercept", "obscured"]):
            return "element_not_clickable"
        if any(k in e for k in ["stale", "detached", "execution context was destroyed"]):
            return "stale_selector"
        if any(k in e for k in ["frame", "iframe"]) or "frame" in logs:
            return "wrong_frame"
        if any(k in e for k in ["modal", "overlay", "dialog blocked"]) or "modal" in logs:
            return "modal_blocking"
        if any(k in e for k in ["unauthorized", "forbidden", "session", "login", "auth"]) or any(
            k in u + " " + t for k in ["login", "signin", "auth"]
        ):
            return "auth_expired"
        if any(k in e for k in ["download", "save file", "file picker"]):
            return "download_issue"
        if loading_state and loading_state != "complete":
            return "page_loading"
        return "element_not_found"
