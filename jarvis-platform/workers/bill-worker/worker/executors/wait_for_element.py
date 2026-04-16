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
    url = payload.get("url") or fallback_url

    if not selector:
        raise ValueError("Missing required 'selector' in task payload")
    if not url:
        raise ValueError("Missing 'url' for wait_for_element. Provide payload.url or run a URL task first.")

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
                progress_callback(f"wait for selector: {selector}")
            page.wait_for_selector(selector, timeout=timeout_ms)
            print(f"[worker] element found: {selector}")
        finally:
            browser.close()

    return {
        "task_type": "wait_for_element",
        "url": url,
        "selector": selector,
        "timeout_ms": timeout_ms,
        "execution_mode": execution_mode,
        "status": "ok",
    }
