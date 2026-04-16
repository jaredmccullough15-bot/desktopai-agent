from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Callable
import time

from playwright.sync_api import Download, Page, sync_playwright


@dataclass
class WorkflowExecutionError(Exception):
    message: str
    result_json: dict[str, Any]

    def __str__(self) -> str:
        return self.message


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


def _take_screenshot(page: Page, screenshots_dir: Path, step_index: int, name: str | None = None) -> dict[str, str]:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = name or f"step_{step_index}"
    filename = f"workflow_{timestamp}_{suffix}.png"
    path = screenshots_dir / filename
    page.screenshot(path=str(path), full_page=True)
    return {
        "filename": filename,
        "local_path": str(path),
        "saved_at": datetime.utcnow().isoformat(),
    }


def _save_dom_snapshot(page: Page, snapshots_dir: Path, step_index: int, name: str | None = None) -> dict[str, str]:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = name or f"step_{step_index}"
    filename = f"dom_{timestamp}_{suffix}.html"
    path = snapshots_dir / filename
    html = page.content()
    path.write_text(html, encoding="utf-8")
    return {
        "filename": filename,
        "local_path": str(path),
        "saved_at": datetime.utcnow().isoformat(),
    }


def _selector_candidates(step: dict[str, Any], selector_strategy: str) -> list[str]:
    selectors = step.get("selectors")
    if isinstance(selectors, list):
        normalized = [str(item).strip() for item in selectors if str(item).strip()]
    else:
        selector = str(step.get("selector") or "").strip()
        normalized = [selector] if selector else []

    if not normalized:
        return []

    if selector_strategy == "strict":
        return normalized[:1]
    return normalized


def _resolve_secret_references(value: Any, secret_resolver: Callable[[str], str] | None) -> Any:
    if isinstance(value, dict):
        if "value_from_secret" in value:
            if not secret_resolver:
                raise ValueError("Step uses value_from_secret, but no secret resolver is configured")

            secret_key = value.get("value_from_secret")
            if not isinstance(secret_key, str) or not secret_key.strip():
                raise ValueError("value_from_secret must be a non-empty string")
            return secret_resolver(secret_key)

        return {key: _resolve_secret_references(item, secret_resolver) for key, item in value.items()}

    if isinstance(value, list):
        return [_resolve_secret_references(item, secret_resolver) for item in value]

    return value


def _save_download(download: Download, downloads_dir: Path) -> dict[str, str]:
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suggested_name = download.suggested_filename or "download.bin"
    filename = f"{timestamp}_{suggested_name}"
    path = downloads_dir / filename
    download.save_as(str(path))
    return {
        "filename": filename,
        "local_path": str(path),
        "timestamp": datetime.utcnow().isoformat(),
    }


def run(
    payload: dict,
    secret_resolver: Callable[[str], str] | None = None,
    progress_callback: Callable[[str], None] | None = None,
    default_mode: str = "interactive_visible",
) -> dict:
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("browser_workflow requires a non-empty 'steps' list")

    execution_mode = str(payload.get("mode") or default_mode or "interactive_visible")
    if execution_mode not in {"interactive_visible", "headless_background"}:
        raise ValueError("Unsupported mode. Use 'interactive_visible' or 'headless_background'")

    headless = execution_mode != "interactive_visible"
    step_delay_ms = int(payload.get("step_delay_ms", 700 if execution_mode == "interactive_visible" else 0))
    selector_strategy = str(payload.get("selector_strategy") or "balanced").strip().lower()
    if selector_strategy not in {"strict", "balanced", "fallback"}:
        selector_strategy = "balanced"

    debug_outputs = payload.get("debug_outputs") if isinstance(payload.get("debug_outputs"), dict) else {}
    capture_debug_screenshots = bool(debug_outputs.get("screenshots", False))
    capture_dom_snapshots = bool(debug_outputs.get("dom_snapshots", False))

    worker_root = Path(__file__).resolve().parents[2]
    screenshots_cfg = os.getenv("BILL_WORKER_SCREENSHOTS_DIR") or os.getenv("JARVIS_WORKER_SCREENSHOTS_DIR")
    downloads_cfg = os.getenv("BILL_WORKER_DOWNLOADS_DIR") or os.getenv("JARVIS_WORKER_DOWNLOADS_DIR")

    screenshots_dir = Path(screenshots_cfg) if screenshots_cfg else (worker_root / "screenshots")
    downloads_dir = Path(downloads_cfg) if downloads_cfg else (worker_root / "downloads")
    dom_snapshots_dir = screenshots_dir / "dom_snapshots"

    if not screenshots_dir.is_absolute():
        screenshots_dir = (worker_root / screenshots_dir).resolve()
    if not downloads_dir.is_absolute():
        downloads_dir = (worker_root / downloads_dir).resolve()

    screenshots_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    if capture_dom_snapshots:
        dom_snapshots_dir.mkdir(parents=True, exist_ok=True)

    screenshots: list[dict[str, str]] = []
    dom_snapshots: list[dict[str, str]] = []
    downloads: list[dict[str, str]] = []
    executed_steps: list[dict[str, Any]] = []
    current_url: str | None = None
    processed_download_objects: set[int] = set()
    async_downloads: list[Download] = []

    if execution_mode == "interactive_visible":
        print("[worker] visible execution mode enabled. Do not use this machine simultaneously during automation.")

    print(f"[worker] browser launched (mode={execution_mode})")
    with sync_playwright() as playwright:
        browser = _launch_browser(playwright, headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        def on_download(download: Download) -> None:
            async_downloads.append(download)

        page.on("download", on_download)

        try:
            for index, raw_step in enumerate(steps, start=1):
                step = _resolve_secret_references(raw_step, secret_resolver)
                action = step.get("action")
                step_start = datetime.utcnow().isoformat()
                step_reason = "completed"
                print(f"[worker] workflow step {index}: action={action}")
                if progress_callback:
                    progress_callback(f"step {index}/{len(steps)}: {action}")

                if action == "open_url":
                    url = step.get("url")
                    if not url:
                        raise ValueError("open_url step requires 'url'")
                    page.goto(url, wait_until="load", timeout=60000)
                    current_url = page.url
                    print(f"[worker] navigated to URL: {current_url}")

                elif action == "wait_for_element":
                    timeout_ms = int(step.get("timeout_ms", 15000))
                    candidates = _selector_candidates(step, selector_strategy)
                    if not candidates:
                        raise ValueError("wait_for_element step requires 'selector'")
                    wait_error: Exception | None = None
                    for selector in candidates:
                        try:
                            page.wait_for_selector(selector, timeout=timeout_ms)
                            print(f"[worker] element found: {selector}")
                            wait_error = None
                            break
                        except Exception as error:
                            wait_error = error
                    if wait_error is not None:
                        raise wait_error

                elif action == "type_text":
                    value = step.get("value")
                    timeout_ms = int(step.get("timeout_ms", 15000))
                    candidates = _selector_candidates(step, selector_strategy)
                    if not candidates:
                        raise ValueError("type_text step requires 'selector'")
                    if value is None:
                        raise ValueError("type_text step requires 'value'")
                    type_error: Exception | None = None
                    for selector in candidates:
                        try:
                            page.fill(selector, str(value), timeout=timeout_ms)
                            print(f"[worker] typed text into selector: {selector}")
                            type_error = None
                            break
                        except Exception as error:
                            type_error = error
                    if type_error is not None:
                        raise type_error

                elif action == "click_selector":
                    timeout_ms = int(step.get("timeout_ms", 15000))
                    candidates = _selector_candidates(step, selector_strategy)
                    if not candidates:
                        raise ValueError("click_selector step requires 'selector'")

                    expect_download = bool(step.get("expect_download") or step.get("wait_for_download"))
                    click_error: Exception | None = None
                    for selector in candidates:
                        try:
                            if expect_download:
                                with page.expect_download(timeout=timeout_ms) as download_info:
                                    page.click(selector, timeout=timeout_ms)

                                download = download_info.value
                                download_meta = _save_download(download, downloads_dir)
                                downloads.append(download_meta)
                                processed_download_objects.add(id(download))
                                print(f"[worker] clicked selector and captured download: {download_meta['local_path']}")
                            else:
                                page.click(selector, timeout=timeout_ms)
                                print(f"[worker] clicked selector: {selector}")
                            click_error = None
                            break
                        except Exception as error:
                            click_error = error
                    if click_error is not None:
                        raise click_error

                elif action == "download_file":
                    timeout_ms = int(step.get("timeout_ms", 30000))
                    candidates = _selector_candidates(step, selector_strategy)
                    if not candidates:
                        raise ValueError("download_file step requires 'selector'")

                    download_error: Exception | None = None
                    for selector in candidates:
                        try:
                            with page.expect_download(timeout=timeout_ms) as download_info:
                                page.click(selector, timeout=timeout_ms)

                            download = download_info.value
                            download_meta = _save_download(download, downloads_dir)
                            downloads.append(download_meta)
                            processed_download_objects.add(id(download))
                            print(f"[worker] download captured: {download_meta['local_path']}")
                            download_error = None
                            break
                        except Exception as error:
                            download_error = error
                    if download_error is not None:
                        raise download_error

                elif action == "take_screenshot":
                    screenshot = _take_screenshot(page, screenshots_dir, index, step.get("name"))
                    screenshots.append(screenshot)
                    print(f"[worker] screenshot saved: {screenshot['local_path']}")

                else:
                    raise ValueError(f"Unsupported workflow action: {action}")

                if capture_debug_screenshots and action != "take_screenshot":
                    screenshot = _take_screenshot(page, screenshots_dir, index, f"debug_step_{index}")
                    screenshots.append(screenshot)
                if capture_dom_snapshots:
                    dom_meta = _save_dom_snapshot(page, dom_snapshots_dir, index, f"step_{index}")
                    dom_snapshots.append(dom_meta)

                executed_steps.append(
                    {
                        "index": index,
                        "step_name": str(step.get("name") or action),
                        "action": action,
                        "status": "ok",
                        "success": True,
                        "reason": step_reason,
                        "retries_attempted": 0,
                        "started_at": step_start,
                        "finished_at": datetime.utcnow().isoformat(),
                    }
                )

                if step_delay_ms > 0:
                    time.sleep(step_delay_ms / 1000)

            for download in async_downloads:
                if id(download) in processed_download_objects:
                    continue
                try:
                    download_meta = _save_download(download, downloads_dir)
                    downloads.append(download_meta)
                    processed_download_objects.add(id(download))
                    print(f"[worker] async download captured: {download_meta['local_path']}")
                except Exception as download_error:
                    print(f"[worker] failed to save async download: {download_error}")

            result = {
                "task_type": "browser_workflow",
                "status": "completed",
                "steps_executed": len(executed_steps),
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "downloads": downloads,
                "dom_snapshots": dom_snapshots,
                "execution_mode": execution_mode,
                "selector_strategy": selector_strategy,
                "final_url": page.url or current_url,
                "saved_at": datetime.utcnow().isoformat(),
            }
            return result

        except Exception as error:
            executed_steps.append(
                {
                    "index": len(executed_steps) + 1,
                    "step_name": "workflow_step",
                    "action": "unknown",
                    "status": "failed",
                    "success": False,
                    "reason": str(error),
                    "retries_attempted": 0,
                    "started_at": datetime.utcnow().isoformat(),
                    "finished_at": datetime.utcnow().isoformat(),
                }
            )
            if capture_debug_screenshots and page:
                try:
                    screenshots.append(_take_screenshot(page, screenshots_dir, len(executed_steps) + 1, "error"))
                except Exception:
                    pass
            if capture_dom_snapshots and page:
                try:
                    dom_snapshots.append(_save_dom_snapshot(page, dom_snapshots_dir, len(executed_steps) + 1, "error"))
                except Exception:
                    pass
            fail_result = {
                "task_type": "browser_workflow",
                "status": "failed",
                "steps_executed": len(executed_steps),
                "executed_steps": executed_steps,
                "screenshots": screenshots,
                "dom_snapshots": dom_snapshots,
                "downloads": downloads,
                "execution_mode": execution_mode,
                "selector_strategy": selector_strategy,
                "error": str(error),
                "final_url": page.url if page else current_url,
                "saved_at": datetime.utcnow().isoformat(),
            }
            raise WorkflowExecutionError(f"browser_workflow failed: {error}", fail_result) from error

        finally:
            context.close()
            browser.close()
