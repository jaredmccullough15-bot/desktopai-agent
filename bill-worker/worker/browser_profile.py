from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen


DEFAULT_PROFILE_DIRECTORY = "Default"
DEFAULT_REMOTE_DEBUGGING_PORT = 9222
DEFAULT_POLICY = "bill_profile"
SUPPORTED_POLICIES = {"bill_profile", "isolated_temp_profile", "attach_existing_debug"}
DEFAULT_BOOKMARK_FOLDERS = ["Bill Core", "TrackVia", "HealthSherpa", "CRM", "Carrier Portals"]


def _log(logger: Callable[[str], None] | None, message: str) -> None:
    if logger:
        logger(message)
    else:
        print(message)


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _extract_bookmarks(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        url = str(row.get("url") or "").strip()
        if not name or not url:
            continue
        folder = str(row.get("folder") or "Bill Core").strip() or "Bill Core"
        enabled = _to_bool(row.get("enabled"), True)
        if not enabled:
            continue
        normalized.append({"name": name, "url": url, "folder": folder, "enabled": enabled})
    return normalized


def resolve_bill_chrome_profile(payload: dict[str, Any], executor_name: str = "unknown") -> dict[str, Any]:
    env = os.environ
    local_app_data = env.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    default_profile_dir = Path(local_app_data) / "BillCore" / "ChromeProfiles" / "BillTeaching"

    policy_raw = str(payload.get("browser_profile_policy") or "").strip().lower()
    policy = policy_raw if policy_raw in SUPPORTED_POLICIES else DEFAULT_POLICY

    profile_dir_raw = str(
        payload.get("bill_chrome_profile_dir")
        or env.get("BILL_WORKER_CHROME_PROFILE_DIR")
        or env.get("JARVIS_WORKER_CHROME_PROFILE_DIR")
        or default_profile_dir
    ).strip()
    profile_dir = Path(os.path.expandvars(profile_dir_raw)).expanduser()

    profile_directory = str(
        payload.get("chrome_profile_directory")
        or env.get("BILL_WORKER_CHROME_PROFILE_DIRECTORY")
        or env.get("JARVIS_WORKER_CHROME_PROFILE_DIRECTORY")
        or DEFAULT_PROFILE_DIRECTORY
    ).strip() or DEFAULT_PROFILE_DIRECTORY

    remote_debugging_port = _to_int(
        payload.get("remote_debugging_port")
        or env.get("BILL_WORKER_REMOTE_DEBUGGING_PORT")
        or env.get("JARVIS_WORKER_REMOTE_DEBUGGING_PORT"),
        DEFAULT_REMOTE_DEBUGGING_PORT,
    )
    if remote_debugging_port <= 0:
        remote_debugging_port = DEFAULT_REMOTE_DEBUGGING_PORT

    prefer_system_chrome = _to_bool(
        payload.get("prefer_system_chrome")
        if payload.get("prefer_system_chrome") is not None
        else env.get("BILL_WORKER_PREFER_SYSTEM_CHROME", env.get("JARVIS_WORKER_PREFER_SYSTEM_CHROME")),
        True,
    )

    cdp_url = str(payload.get("cdp_url") or f"http://127.0.0.1:{remote_debugging_port}").strip()
    force_fresh = _to_bool(payload.get("force_fresh"), False)

    bookmarks = _extract_bookmarks(
        payload.get("bill_bookmarks")
        if payload.get("bill_bookmarks") is not None
        else _extract_bookmarks_json_from_env()
    )

    profile_dir.mkdir(parents=True, exist_ok=True)

    return {
        "executor_name": executor_name,
        "browser_profile_policy": policy,
        "bill_chrome_profile_dir": profile_dir,
        "chrome_profile_directory": profile_directory,
        "remote_debugging_port": remote_debugging_port,
        "cdp_url": cdp_url,
        "prefer_system_chrome": prefer_system_chrome,
        "force_fresh": force_fresh,
        "bill_bookmarks": bookmarks,
        "browser_mode_selected": "system_chrome_cdp" if policy in {"bill_profile", "attach_existing_debug"} else "isolated_playwright",
    }


def _extract_bookmarks_json_from_env() -> list[dict[str, Any]]:
    raw = os.environ.get("BILL_WORKER_BOOKMARKS_JSON") or os.environ.get("JARVIS_WORKER_BOOKMARKS_JSON")
    if not raw:
        return []
    try:
        return _extract_bookmarks(json.loads(raw))
    except Exception:
        return []


def _detect_system_chrome_path() -> Path | None:
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _chrome_timestamp_now() -> str:
    windows_epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    micros = int((now - windows_epoch).total_seconds() * 1_000_000)
    return str(micros)


def _default_bookmarks_payload() -> dict[str, Any]:
    now = _chrome_timestamp_now()
    return {
        "checksum": "",
        "roots": {
            "bookmark_bar": {
                "children": [],
                "date_added": now,
                "date_last_used": "0",
                "date_modified": now,
                "id": "1",
                "name": "Bookmarks bar",
                "type": "folder",
            },
            "other": {
                "children": [],
                "date_added": now,
                "date_last_used": "0",
                "date_modified": now,
                "id": "2",
                "name": "Other bookmarks",
                "type": "folder",
            },
            "synced": {
                "children": [],
                "date_added": now,
                "date_last_used": "0",
                "date_modified": now,
                "id": "3",
                "name": "Mobile bookmarks",
                "type": "folder",
            },
        },
        "version": 1,
    }


def _iter_nodes(node: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def walk(current: dict[str, Any]) -> None:
        out.append(current)
        for child in current.get("children") or []:
            if isinstance(child, dict):
                walk(child)

    walk(node)
    return out


def _next_node_id(payload: dict[str, Any]) -> int:
    max_id = 0
    roots = payload.get("roots") if isinstance(payload, dict) else {}
    if not isinstance(roots, dict):
        roots = {}
    for root in roots.values():
        if not isinstance(root, dict):
            continue
        for node in _iter_nodes(root):
            try:
                node_id = int(str(node.get("id", "0")))
            except Exception:
                node_id = 0
            max_id = max(max_id, node_id)
    return max_id + 1


def _get_or_create_folder(root_folder: dict[str, Any], folder_name: str, next_id: Callable[[], str]) -> dict[str, Any]:
    children = root_folder.setdefault("children", [])
    for child in children:
        if isinstance(child, dict) and child.get("type") == "folder" and str(child.get("name") or "") == folder_name:
            return child

    now = _chrome_timestamp_now()
    folder = {
        "children": [],
        "date_added": now,
        "date_last_used": "0",
        "date_modified": now,
        "id": next_id(),
        "name": folder_name,
        "type": "folder",
    }
    children.append(folder)
    root_folder["date_modified"] = now
    return folder


def _load_or_create_bookmarks_payload(bookmarks_path: Path) -> dict[str, Any]:
    if bookmarks_path.exists():
        try:
            data = json.loads(bookmarks_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("roots"), dict):
                return data
        except Exception:
            pass
    return _default_bookmarks_payload()


def _is_bill_profile_chrome_running(profile_dir: Path) -> bool:
    target = str(profile_dir).lower().replace("\\", "\\\\")
    commands = [
        [
            "wmic",
            "process",
            "where",
            "name='chrome.exe'",
            "get",
            "CommandLine",
            "/format:list",
        ],
        [
            "wmic",
            "path",
            "win32_process",
            "where",
            "name='chrome.exe'",
            "get",
            "CommandLine",
            "/format:list",
        ],
    ]
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
            output = f"{result.stdout}\n{result.stderr}".lower()
            if target in output and "--user-data-dir" in output:
                return True
        except Exception:
            continue
    return False


def _terminate_bill_profile_chrome(profile_dir: Path) -> int:
    target = str(profile_dir).replace("'", "''")
    try:
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                f"name='chrome.exe' and CommandLine like '%--user-data-dir={target}%'",
                "call",
                "terminate",
            ],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
        output = f"{result.stdout}\n{result.stderr}"
        if "ReturnValue = 0" in output:
            return output.count("ReturnValue = 0")
    except Exception:
        pass
    return 0


def provision_bill_bookmarks(profile_dir: Path, bookmarks: list[dict[str, Any]]) -> dict[str, Any]:
    profile_path = Path(profile_dir)
    default_profile = profile_path / DEFAULT_PROFILE_DIRECTORY
    default_profile.mkdir(parents=True, exist_ok=True)
    bookmarks_path = default_profile / "Bookmarks"

    if _is_bill_profile_chrome_running(profile_path):
        return {
            "status": "skipped_profile_running",
            "bookmarks_path": str(bookmarks_path),
            "added": [],
            "updated": [],
            "skipped": ["Chrome is running with Bill profile; skipping bookmark write"],
            "bookmarks_ready": True,
        }

    payload = _load_or_create_bookmarks_payload(bookmarks_path)
    roots = payload.setdefault("roots", {})
    bar = roots.get("bookmark_bar")
    if not isinstance(bar, dict):
        now = _chrome_timestamp_now()
        bar = {
            "children": [],
            "date_added": now,
            "date_last_used": "0",
            "date_modified": now,
            "id": "1",
            "name": "Bookmarks bar",
            "type": "folder",
        }
        roots["bookmark_bar"] = bar

    next_id = _next_node_id(payload)

    def alloc_id() -> str:
        nonlocal next_id
        value = str(next_id)
        next_id += 1
        return value

    for folder_name in DEFAULT_BOOKMARK_FOLDERS:
        _get_or_create_folder(bar, folder_name, alloc_id)

    added: list[str] = []
    updated: list[str] = []
    skipped: list[str] = []

    for item in bookmarks:
        if not isinstance(item, dict):
            continue
        if not _to_bool(item.get("enabled"), True):
            continue

        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        folder_name = str(item.get("folder") or "Bill Core").strip() or "Bill Core"
        if not name or not url:
            continue

        folder = _get_or_create_folder(bar, folder_name, alloc_id)
        children = folder.setdefault("children", [])

        exact_match = None
        same_name = None
        for child in children:
            if not isinstance(child, dict) or child.get("type") != "url":
                continue
            child_name = str(child.get("name") or "")
            child_url = str(child.get("url") or "")
            if child_name == name and child_url == url:
                exact_match = child
                break
            if child_name == name:
                same_name = child

        label = f"{folder_name} / {name}"
        if exact_match is not None:
            skipped.append(f"{label} (already_exists)")
            continue

        now = _chrome_timestamp_now()
        if same_name is not None:
            same_name["url"] = url
            same_name["date_modified"] = now
            updated.append(label)
            continue

        children.append(
            {
                "date_added": now,
                "id": alloc_id(),
                "name": name,
                "type": "url",
                "url": url,
            }
        )
        added.append(label)

    bookmarks_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    return {
        "status": "ok",
        "bookmarks_path": str(bookmarks_path),
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "bookmarks_ready": True,
    }


def _debug_port_ready(port: int, timeout_seconds: float = 8.0) -> bool:
    deadline = time.time() + max(0.5, timeout_seconds)
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            req = Request(url, headers={"User-Agent": "BillWorker/1.0"})
            with urlopen(req, timeout=1.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)
    return False


def launch_bill_chrome_with_debug(
    profile_config: dict[str, Any],
    start_url: str | None = None,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    profile_dir = Path(profile_config["bill_chrome_profile_dir"])
    profile_directory = str(profile_config.get("chrome_profile_directory") or DEFAULT_PROFILE_DIRECTORY)
    port = int(profile_config.get("remote_debugging_port") or DEFAULT_REMOTE_DEBUGGING_PORT)
    force_fresh = bool(profile_config.get("force_fresh"))

    running = _is_bill_profile_chrome_running(profile_dir)
    if running and force_fresh:
        terminated = _terminate_bill_profile_chrome(profile_dir)
        _log(logger, f"[worker] bill-profile force_fresh requested; terminated_instances={terminated}")
        running = _is_bill_profile_chrome_running(profile_dir)
    elif running and not force_fresh:
        _log(logger, "[worker] bill-profile already running; reusing existing profile instance")

    chrome_path = _detect_system_chrome_path()
    if chrome_path is None:
        raise RuntimeError("System Chrome not found; cannot launch Bill profile browser")

    launch_args = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        f"--profile-directory={profile_directory}",
        "--start-maximized",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if start_url:
        launch_args.append(str(start_url))

    launched = False
    if not running:
        subprocess.Popen(launch_args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        launched = True

    ready = _debug_port_ready(port)

    return {
        "launched": launched,
        "launch_command": launch_args,
        "debug_port_ready": ready,
        "remote_debugging_port": port,
        "chrome_path": str(chrome_path),
    }


def attach_playwright_to_bill_chrome(playwright: Any, profile_config: dict[str, Any], logger: Callable[[str], None] | None = None):
    cdp_url = str(profile_config.get("cdp_url") or f"http://127.0.0.1:{profile_config.get('remote_debugging_port', DEFAULT_REMOTE_DEBUGGING_PORT)}")
    _log(logger, f"[worker] attaching Playwright to Bill profile CDP: {cdp_url}")
    return playwright.chromium.connect_over_cdp(cdp_url)


def get_browser_context_for_task(
    playwright: Any,
    payload: dict[str, Any],
    executor_name: str,
    headless: bool,
    accept_downloads: bool = False,
    start_url: str | None = None,
    logger: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    profile = resolve_bill_chrome_profile(payload, executor_name=executor_name)
    policy = profile["browser_profile_policy"]

    bookmarks_result: dict[str, Any] = {
        "status": "not_applicable",
        "bookmarks_path": "",
        "added": [],
        "updated": [],
        "skipped": [],
        "bookmarks_ready": policy != "bill_profile",
    }
    debug_status: dict[str, Any] = {
        "launched": False,
        "launch_command": [],
        "debug_port_ready": policy != "bill_profile",
        "remote_debugging_port": profile["remote_debugging_port"],
    }

    browser = None
    context = None
    page = None
    should_close_browser = False
    should_close_context = False

    if policy == "bill_profile":
        bookmarks_result = provision_bill_bookmarks(profile["bill_chrome_profile_dir"], profile.get("bill_bookmarks") or [])
        debug_status = launch_bill_chrome_with_debug(profile, start_url=start_url, logger=logger)
        browser = attach_playwright_to_bill_chrome(playwright, profile, logger=logger)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
    elif policy == "attach_existing_debug":
        browser = playwright.chromium.connect_over_cdp(profile["cdp_url"])
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
    else:
        try:
            browser = playwright.chromium.launch(headless=headless)
        except Exception as chromium_error:
            _log(logger, f"[worker] chromium launch failed, trying msedge fallback: {chromium_error}")
            browser = playwright.chromium.launch(headless=headless, channel="msedge")
        context = browser.new_context(accept_downloads=accept_downloads)
        page = context.new_page()
        should_close_browser = True
        should_close_context = True

    log_payload = {
        "executor_name": executor_name,
        "browser_profile_policy": policy,
        "profile_path": str(profile["bill_chrome_profile_dir"]),
        "profile_directory": str(profile["chrome_profile_directory"]),
        "bookmarks_provisioned": bool(bookmarks_result.get("status") in {"ok", "skipped_profile_running"}),
        "remote_debug_port": int(profile["remote_debugging_port"]),
        "browser_mode_selected": profile["browser_mode_selected"],
    }
    _log(logger, "[worker] browser-profile " + json.dumps(log_payload, sort_keys=True))

    return {
        "browser": browser,
        "context": context,
        "page": page,
        "should_close_browser": should_close_browser,
        "should_close_context": should_close_context,
        "profile": profile,
        "bookmarks": bookmarks_result,
        "debug": debug_status,
        "bill_profile_ready": policy != "isolated_temp_profile",
        "bookmarks_ready": bool(bookmarks_result.get("bookmarks_ready", False)),
        "debug_port_ready": bool(debug_status.get("debug_port_ready", False)),
    }
