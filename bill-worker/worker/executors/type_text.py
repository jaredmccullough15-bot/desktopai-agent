from __future__ import annotations

from typing import Callable

from playwright.sync_api import sync_playwright
from worker.browser_profile import get_browser_context_for_task


def run(
    payload: dict,
    fallback_url: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
    default_mode: str = "headless_background",
) -> dict:
    selector = payload.get("selector")
    value = payload.get("value")
    url = payload.get("url") or fallback_url

    if not selector:
        raise ValueError("Missing required 'selector' in task payload")
    if value is None:
        raise ValueError("Missing required 'value' in task payload")
    if not url:
        raise ValueError("Missing 'url' for type_text. Provide payload.url or run a URL task first.")

    execution_mode = str(payload.get("mode") or default_mode or "headless_background")
    if execution_mode not in {"interactive_visible", "headless_background"}:
        raise ValueError("Unsupported mode. Use 'interactive_visible' or 'headless_background'")

    headless = execution_mode != "interactive_visible"

    timeout_ms = int(payload.get("timeout_ms", 15000))

    if progress_callback:
        progress_callback("launch browser")
    bundle: dict = {}
    print(f"[worker] browser launched (mode={execution_mode})")
    with sync_playwright() as playwright:
        bundle = get_browser_context_for_task(
            playwright=playwright,
            payload=payload,
            executor_name="type_text",
            headless=headless,
            start_url=str(url),
            logger=print,
        )
        browser = bundle["browser"]
        context = bundle["context"]
        page = bundle["page"]
        try:
            if progress_callback:
                progress_callback(f"open url: {url}")
            page.goto(url, wait_until="load", timeout=60000)
            print(f"[worker] navigated to URL: {url}")
            if progress_callback:
                progress_callback(f"type text into selector: {selector}")
            page.fill(selector, str(value), timeout=timeout_ms)
            print(f"[worker] typed into selector: {selector}")
        finally:
            if bundle.get("should_close_context") and context is not None:
                context.close()
            if bundle.get("should_close_browser") and browser is not None:
                browser.close()

    return {
        "task_type": "type_text",
        "url": url,
        "selector": selector,
        "value": str(value),
        "timeout_ms": timeout_ms,
        "execution_mode": execution_mode,
        "browser_profile_policy": bundle.get("profile", {}).get("browser_profile_policy", "bill_profile"),
        "bill_profile_ready": bool(bundle.get("bill_profile_ready", False)),
        "bookmarks_ready": bool(bundle.get("bookmarks_ready", False)),
        "debug_port_ready": bool(bundle.get("debug_port_ready", False)),
        "profile_path": str(bundle.get("profile", {}).get("bill_chrome_profile_dir", "")),
        "profile_directory": str(bundle.get("profile", {}).get("chrome_profile_directory", "")),
        "remote_debugging_port": int(bundle.get("profile", {}).get("remote_debugging_port", 0) or 0),
        "browser_mode_selected": str(bundle.get("profile", {}).get("browser_mode_selected", "")),
        "executor_name": "type_text",
        "status": "ok",
    }
