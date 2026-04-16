from __future__ import annotations

from typing import Callable

from playwright.sync_api import sync_playwright


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
    print(f"[worker] browser launched (mode={execution_mode})")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        try:
            page = browser.new_page()
            if progress_callback:
                progress_callback(f"open url: {url}")
            page.goto(url, wait_until="load", timeout=60000)
            print(f"[worker] navigated to URL: {url}")
            if progress_callback:
                progress_callback(f"type text into selector: {selector}")
            page.fill(selector, str(value), timeout=timeout_ms)
            print(f"[worker] typed into selector: {selector}")
        finally:
            browser.close()

    return {
        "task_type": "type_text",
        "url": url,
        "selector": selector,
        "value": str(value),
        "timeout_ms": timeout_ms,
        "execution_mode": execution_mode,
        "status": "ok",
    }
