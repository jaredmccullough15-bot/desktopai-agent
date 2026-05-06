from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Callable
import time

from playwright.sync_api import sync_playwright
from worker.browser_profile import get_browser_context_for_task


def run(
    payload: dict,
    progress_callback: Callable[[str], None] | None = None,
    default_mode: str = "interactive_visible",
) -> dict:
    url = payload.get("url")
    if not url:
        raise ValueError("Missing required 'url' in task payload")

    execution_mode = str(payload.get("mode") or default_mode or "headless_background")
    if execution_mode not in {"interactive_visible", "headless_background"}:
        raise ValueError("Unsupported mode. Use 'interactive_visible' or 'headless_background'")

    headless = execution_mode != "interactive_visible"
    pause_ms = int(payload.get("step_delay_ms", 500 if execution_mode == "interactive_visible" else 0))

    worker_root = Path(__file__).resolve().parents[2]
    configured_dir = os.getenv("BILL_WORKER_SCREENSHOTS_DIR") or os.getenv("JARVIS_WORKER_SCREENSHOTS_DIR")
    screenshots_dir = Path(configured_dir) if configured_dir else (worker_root / "screenshots")
    if not screenshots_dir.is_absolute():
        screenshots_dir = (worker_root / screenshots_dir).resolve()
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    screenshot_path = screenshots_dir / filename
    saved_at = datetime.utcnow().isoformat()

    if execution_mode == "interactive_visible":
        print("[worker] visible execution mode enabled. Do not use this machine simultaneously during automation.")

    if progress_callback:
        progress_callback("launch browser")

    bundle: dict = {}
    print(f"[worker] browser launched (mode={execution_mode})")
    with sync_playwright() as playwright:
        bundle = get_browser_context_for_task(
            playwright=playwright,
            payload=payload,
            executor_name="open_url_and_screenshot",
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
            if pause_ms > 0:
                time.sleep(pause_ms / 1000)
            if progress_callback:
                progress_callback("capture screenshot")
            page.screenshot(path=str(screenshot_path), full_page=True)
        finally:
            if bundle.get("should_close_context") and context is not None:
                context.close()
            if bundle.get("should_close_browser") and browser is not None:
                browser.close()

    print(f"[worker] screenshot saved: {screenshot_path}")
    return {
        "task_type": "open_url_and_screenshot",
        "filename": filename,
        "local_path": str(screenshot_path),
        "url": url,
        "saved_at": saved_at,
        "execution_mode": execution_mode,
        "browser_profile_policy": bundle.get("profile", {}).get("browser_profile_policy", "bill_profile"),
        "bill_profile_ready": bool(bundle.get("bill_profile_ready", False)),
        "bookmarks_ready": bool(bundle.get("bookmarks_ready", False)),
        "debug_port_ready": bool(bundle.get("debug_port_ready", False)),
        "profile_path": str(bundle.get("profile", {}).get("bill_chrome_profile_dir", "")),
        "profile_directory": str(bundle.get("profile", {}).get("chrome_profile_directory", "")),
        "remote_debugging_port": int(bundle.get("profile", {}).get("remote_debugging_port", 0) or 0),
        "browser_mode_selected": str(bundle.get("profile", {}).get("browser_mode_selected", "")),
        "executor_name": "open_url_and_screenshot",
        "status": "ok",
    }
