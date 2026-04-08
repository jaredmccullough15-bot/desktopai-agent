#!/usr/bin/env python3
"""
teach_session.py — Playwright browser instrumentation for Bill Teach Mode.

Launches a visible Chromium browser and observes:
  - URL navigations
  - Element clicks
  - Text input (captured on blur — final value only)
  - Select / dropdown changes

Each observed action is converted to a draft step and appended to the
active workflow learning draft via:
  POST /api/brain/workflow-learning/drafts/{draft_id}/steps/append

Usage:
    python teach_session.py \
        --draft-id <DRAFT_ID> \
        [--api-base http://127.0.0.1:8010] \
        [--start-url https://example.com]

Requirements (install into the same venv as bill-core):
    pip install playwright requests
    playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    print(
        "[teach] 'requests' not installed. Run: pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "[teach] 'playwright' not installed.\n"
        "  Run: pip install playwright && playwright install chromium",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_API_BASE = "http://127.0.0.1:8010"
APPEND_TIMEOUT = 8  # HTTP timeout seconds
EVENT_DEBOUNCE = 0.25  # Ignore exact-duplicate event types within this many seconds

# ── Browser-side listener (injected via add_init_script on every page load) ───
_LISTENER_JS = r"""
(function () {
    // Re-attach on every navigation — guard by storing the token on window so
    // we only ever attach ONE set of listeners even if the script re-runs.
    if (window.__billListenersAttached) { return; }
    window.__billListenersAttached = true;

    // Push events into a per-frame JS queue.  Python drains it via
    // frame.evaluate() on a 200 ms polling loop — no console.log used,
    // immune to console overrides, CSP, and cross-origin restrictions.
    if (!Array.isArray(window.__billEvents)) { window.__billEvents = []; }
    function emit(payload) {
        try { window.__billEvents.push(payload); }
        catch (err) { /* ignore */ }
    }

    function esc(s) { return s ? String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') : ''; }

    function getInfo(el) {
        if (!el || el === document || el === document.body) return {};
        return {
            tag:         String(el.tagName || '').toLowerCase(),
            id:          el.id || '',
            name:        el.getAttribute('name')        || '',
            class_name:  typeof el.className === 'string' ? el.className : '',
            aria_label:  el.getAttribute('aria-label')  || '',
            data_testid: el.getAttribute('data-testid') || '',
            placeholder: el.getAttribute('placeholder') || '',
            text:        String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
            input_type:  String(el.getAttribute('type') || '').toLowerCase(),
            value:       el.value != null ? String(el.value) : '',
            href:        el.href  || '',
            role:        el.getAttribute('role') || '',
        };
    }

    function buildSelector(info) {
        if (info.id)
            return '#' + info.id.replace(/([^\w-])/g, '\\$1');
        if (info.data_testid)
            return '[data-testid="' + esc(info.data_testid) + '"]';
        if (info.aria_label)
            return '[aria-label="' + esc(info.aria_label) + '"]';
        if (info.name && ['input','select','textarea'].indexOf(info.tag) !== -1)
            return info.tag + '[name="' + esc(info.name) + '"]';
        if (info.text && ['button','a'].indexOf(info.tag) !== -1 && info.text.length < 50)
            return info.tag + ':has-text("' + esc(info.text.slice(0, 40)) + '")';
        if (info.class_name && info.tag) {
            var classes = info.class_name.trim().split(/\s+/)
                .filter(function(c) {
                    return c.length > 1 && c.length < 30 && !/[:()[\]{}]/.test(c);
                }).slice(0, 2);
            if (classes.length) return info.tag + '.' + classes.join('.');
        }
        return info.tag || 'div';
    }

    // Walk up the DOM to find the most meaningful interactive ancestor
    function findInteractive(el) {
        for (var i = 0; i < 8; i++) {
            if (!el || el === document.body) break;
            var t = String(el.tagName || '').toLowerCase();
            var role = el.getAttribute('role') || '';
            if (t === 'button' || t === 'a' || t === 'input' ||
                t === 'select' || t === 'textarea' ||
                role === 'button' || role === 'link' || role === 'tab' ||
                role === 'menuitem' || role === 'option' ||
                el.getAttribute('tabindex') === '0') {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    }

    /* ── Click ────────────────────────────────────────────── */
    document.addEventListener('click', function (e) {
        var raw = e.target;
        var el = findInteractive(raw) || raw;
        var info = getInfo(el);

        // Skip pure input fields (captured on blur instead)
        var t = info.tag;
        if (t === 'input' || t === 'textarea' || t === 'select') return;

        emit({
            event_type: 'click',
            selector:   buildSelector(info),
            element:    info,
            url:        window.location.href,
            ts:         Date.now(),
        });
    }, true);

    /* ── Text input (on blur = final value) ─────────────── */
    document.addEventListener('blur', function (e) {
        var el = e.target;
        if (!el) return;
        var t = String(el.tagName || '').toLowerCase();
        if (t !== 'input' && t !== 'textarea') return;
        if (!el.value) return;
        if (String(el.getAttribute('type') || '').toLowerCase() === 'password') return;
        var info = getInfo(el);
        emit({
            event_type: 'type_text',
            selector:   buildSelector(info),
            value:      el.value,
            element:    info,
            url:        window.location.href,
            ts:         Date.now(),
        });
    }, true);

    /* ── Select / dropdown ──────────────────────────────── */
    document.addEventListener('change', function (e) {
        var el = e.target;
        if (!el || String(el.tagName || '').toLowerCase() !== 'select') return;
        var info = getInfo(el);
        var selectedText = (el.options && el.selectedIndex >= 0)
            ? el.options[el.selectedIndex].text : '';
        emit({
            event_type:  'select_option',
            selector:    buildSelector(info),
            value:       el.value,
            option_text: selectedText,
            element:     info,
            url:         window.location.href,
            ts:          Date.now(),
        });
    }, true);

    emit({event_type: '_attached', url: window.location.href});
}());
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _label(element: dict[str, Any]) -> str:
    return (
        element.get("aria_label")
        or element.get("text")
        or element.get("placeholder")
        or element.get("name")
        or element.get("id")
        or ""
    ).strip()[:60]


def _infer_step_name(event: dict[str, Any]) -> str:
    et = event.get("event_type", "")
    el = event.get("element") or {}
    lbl = _label(el)
    url = event.get("url", "")
    opt = event.get("option_text", "") or event.get("value", "")

    if et == "navigate":
        try:
            path = urlparse(url).path.rstrip("/") or "/"
            return f"Navigate → {path[:60]}"
        except Exception:
            return f"Navigate → {url[:60]}"
    if et == "click":
        return f"Click '{lbl}'" if lbl else "Click element"
    if et == "type_text":
        return f"Fill '{lbl}'" if lbl else "Enter text"
    if et == "select_option":
        return (f"Select '{opt}'" + (f" in '{lbl}'" if lbl else "")) if opt else "Select option"
    return "Perform action"


def _infer_intent(event: dict[str, Any]) -> str:
    et = event.get("event_type", "")
    lbl = _label(event.get("element") or {})
    if et == "navigate":
        return "Navigate to the required page."
    if et == "click":
        return f"Trigger the next step by clicking '{lbl}'." if lbl else "Advance the workflow."
    if et == "type_text":
        return f"Supply required data into '{lbl}'." if lbl else "Provide required input."
    if et == "select_option":
        return f"Set the required option for '{lbl}'." if lbl else "Choose the required dropdown value."
    return ""


_ACTION_MAP = {
    "navigate":      "open_url",
    "click":         "click_selector",
    "type_text":     "type_text",
    "select_option": "select_option",
}


def _event_to_step(event: dict[str, Any]) -> dict[str, Any]:
    et = event.get("event_type", "")
    el = event.get("element") or {}
    return {
        "action":        _ACTION_MAP.get(et, et),
        "step_name":     _infer_step_name(event),
        "intent":        _infer_intent(event),
        "description":   _infer_step_name(event),
        "selector":      event.get("selector", ""),
        "url":           event.get("url", "") if et == "navigate" else "",
        "value":         event.get("value", ""),
        "option":        event.get("option_text", ""),
        "element_label": _label(el),
        "element_tag":   el.get("tag", ""),
        "element_type":  el.get("input_type", ""),
        "captured_at":   datetime.now(timezone.utc).isoformat(),
    }


def _post_step(api_base: str, draft_id: str, step: dict[str, Any]) -> dict[str, Any] | None:
    endpoint = f"{api_base.rstrip('/')}/api/brain/workflow-learning/drafts/{draft_id}/steps/append"
    try:
        resp = requests.post(endpoint, json=step, timeout=APPEND_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [teach] Append failed ({resp.status_code}): {resp.text[:120]}", file=sys.stderr)
    except Exception as exc:
        print(f"  [teach] HTTP error: {exc}", file=sys.stderr)
    return None


# ── Session runner ────────────────────────────────────────────────────────────

def run_session(draft_id: str, api_base: str, start_url: str | None = None) -> None:
    sep = "=" * 62
    print(f"\n{sep}")
    print(f"  Bill Teach Mode — Observation Session")
    print(sep)
    print(f"  Draft    : {draft_id}")
    print(f"  API base : {api_base}")
    if start_url:
        print(f"  Start URL: {start_url}")
    print()
    print(f"  Perform your workflow in the browser.")
    print(f"  Clicks, text entry, and navigation are captured automatically.")
    print(f"  Password fields are never recorded.")
    print(f"  Close the browser window when finished.\n")

    last_event_ts: dict[str, float] = {}
    last_url: list[str] = [""]
    step_num: list[int] = [0]
    step_lock = threading.Lock()

    # ── Background thread drains HTTP posts so Playwright's event
    #    loop is never blocked by a slow/failed HTTP request. ──────
    post_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def _post_worker() -> None:
        while True:
            item = post_queue.get()
            if item is None:        # sentinel → shut down
                post_queue.task_done()
                break
            step = item
            result = _post_step(api_base, draft_id, step)
            if result is not None:
                with step_lock:
                    step_num[0] += 1
                    n = step_num[0]
                name  = step.get("step_name", "?")
                action = step.get("action", "?")
                print(f"  [{n:>3}] {action:<22} {name}")
            post_queue.task_done()

    worker = threading.Thread(target=_post_worker, daemon=True)
    worker.start()

    def _enqueue(step: dict[str, Any]) -> None:
        post_queue.put(step)

    def record(event: dict[str, Any]) -> None:
        et = event.get("event_type", "")
        if et == "_attached":
            print(f"  [listen] Attached on {event.get('url', '?')}")
            return
        now = time.monotonic()
        if now - last_event_ts.get(et, 0.0) < EVENT_DEBOUNCE:
            return
        last_event_ts[et] = now
        _enqueue(_event_to_step(event))

    def on_navigate(url: str) -> None:
        if url == last_url[0]:
            return
        if url.startswith(("about:", "chrome:", "data:", "javascript:")):
            return
        last_url[0] = url
        last_event_ts["navigate"] = time.monotonic()
        _enqueue(_event_to_step({"event_type": "navigate", "url": url, "element": {}}))

    def attach_page(p: Any) -> None:
        p.on("framenavigated", lambda frame: on_navigate(frame.url) if frame == p.main_frame else None)

    def _drain_frames() -> None:
        """Poll every frame in every open page and drain their window.__billEvents.

        JS pushes events into window.__billEvents (a per-frame array).
        frame.evaluate() reads and clears the array atomically from Python.
        This bypasses console.log overrides, CSP, and cross-origin iframe
        restrictions that defeated the previous console.log / CDP approaches.
        """
        try:
            for p in context.pages:
                if p.is_closed():
                    continue
                for frame in p.frames:
                    try:
                        events = frame.evaluate(
                            "() => { var e = window.__billEvents || []; "
                            "window.__billEvents = []; return e; }"
                        )
                        for evt in (events or []):
                            et = evt.get("event_type", "?")
                            if et != "_attached":
                                print(f"  [evt ] received: {et}")
                            record(evt)
                    except Exception:
                        pass
        except Exception:
            pass

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-infobars"],
        )
        context = browser.new_context(viewport=None)
        context.add_init_script(_LISTENER_JS)

        page = context.new_page()
        attach_page(page)

        def on_new_page(new_page: Any) -> None:
            """Attach listeners to pages opened by the workflow (new tabs etc.)."""
            try:
                attach_page(new_page)
            except Exception:
                pass

        context.on("page", on_new_page)

        if start_url:
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            except Exception as exc:
                print(f"  [teach] Could not load start URL: {exc}", file=sys.stderr)

        try:
            while browser.is_connected():
                _drain_frames()
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n  [teach] Interrupted.")
        finally:
            try:
                browser.close()
            except Exception:
                pass
            # Drain remaining queued steps before exiting
            post_queue.put(None)
            worker.join(timeout=30)

    with step_lock:
        total = step_num[0]
    print(f"\n  Session complete. {total} steps captured.")
    print(f"  Open the Bill dashboard to review, enrich, and publish the draft.\n")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bill Teach Mode — Playwright observation browser"
    )
    parser.add_argument("--draft-id", required=True, help="Workflow learning draft ID")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="Bill Core API base URL")
    parser.add_argument("--start-url", default=None, help="Optional URL to open when the browser launches")
    args = parser.parse_args()
    run_session(args.draft_id, args.api_base, args.start_url)


if __name__ == "__main__":
    main()
