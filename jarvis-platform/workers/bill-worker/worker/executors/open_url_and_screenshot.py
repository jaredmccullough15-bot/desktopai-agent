from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
from typing import Callable
import time

from playwright.sync_api import sync_playwright


def _launch_browser(playwright, headless: bool):
    try:
        return playwright.chromium.launch(headless=headless)
    except Exception as chromium_error:
        print(f"[worker] chromium launch failed, trying msedge fallback: {chromium_error}")
        try:
            return playwright.chromium.launch(headless=headless, channel="msedge")
        except Exception as edge_error:
            raise RuntimeError(
                f"Unable to launch browser. Chromium error: {chromium_error}. "
                f"MS Edge fallback error: {edge_error}"
            ) from edge_error


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

    print(f"[worker] browser launched (mode={execution_mode})")
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, headless=headless)
        try:
            page = browser.new_page()
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
            browser.close()

    print(f"[worker] screenshot saved: {screenshot_path}")
    return {
        "task_type": "open_url_and_screenshot",
        "filename": filename,
        "local_path": str(screenshot_path),
        "url": url,
        "saved_at": saved_at,
        "execution_mode": execution_mode,
        "status": "ok",
    }
