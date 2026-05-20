import json
import os
import socket
import subprocess
import sys
import threading
import time
import random
import uuid
import hashlib
import traceback
import platform
from importlib import metadata as importlib_metadata
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from worker.executors.browser_workflow import WorkflowExecutionError, run as run_browser_workflow
from worker.executors.click_selector import run as run_click_selector
from worker.executors.open_url_and_screenshot import run as run_open_url_and_screenshot
from worker.executors.smart_sherpa_sync import run as run_smart_sherpa_sync
from worker.executors.taught_workflow import run as run_taught_workflow
from worker.executors.type_text import run as run_type_text
from worker.executors.wait_for_element import run as run_wait_for_element
from worker.browser_profile import (
    launch_bill_chrome_with_debug,
    provision_bill_bookmarks,
    resolve_bill_chrome_profile,
)

DEFAULT_CORE_URL = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
API_BASE = os.getenv("BILL_CORE_URL") or os.getenv("JARVIS_CORE_URL", DEFAULT_CORE_URL)
APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
STATE_PATH = APP_ROOT / ".worker_state.json"
CONFIG_PATH = APP_ROOT / "config.json"
LEGACY_CONFIG_PATH = APP_ROOT / "worker-config.json"
SECRETS_PATH = APP_ROOT / "secrets.local.json"
LOGS_DIR = APP_ROOT / "logs"
SCREENSHOTS_DIR = APP_ROOT / "screenshots"
DOWNLOADS_DIR = APP_ROOT / "downloads"
WORKER_VERSION = "0.3.33"
HEARTBEAT_INTERVAL_SECONDS = 10.0
POLLING_INTERVAL_SECONDS = 5.0
UPDATE_CHECK_INTERVAL_SECONDS = 120.0
AUTO_UPDATE_ENABLED = True
MACHINE_DISPLAY_NAME_OVERRIDE: str | None = None
DEFAULT_WORKER_MODE = "interactive_visible"
WORKER_UI_ENABLED = True
LOG_LEVEL = "INFO"
PREFER_SYSTEM_CHROME = bool(getattr(sys, "frozen", False))
BILL_CHROME_PROFILE_DIR = Path(os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")) / "BillCore" / "ChromeProfiles" / "BillTeaching"
CHROME_PROFILE_DIRECTORY = "Default"
REMOTE_DEBUGGING_PORT = 9222
BROWSER_PROFILE_POLICY = "bill_profile"
WORKER_SHARED_SECRET = ""

DEFAULT_BILL_BOOKMARKS: list[dict[str, Any]] = [
    {
        "name": "TrackVia Audit Queue",
        "url": "https://go.trackvia.com/",
        "folder": "TrackVia",
        "enabled": True,
    },
    {
        "name": "HealthSherpa",
        "url": "https://www.healthsherpa.com/",
        "folder": "HealthSherpa",
        "enabled": True,
    },
    {
        "name": "Keap / Infusionsoft",
        "url": "https://signin.infusionsoft.com/",
        "folder": "CRM",
        "enabled": True,
    },
    {
        "name": "Ambetter",
        "url": "https://provider.pshpgeorgia.com/",
        "folder": "Carrier Portals",
        "enabled": True,
    },
    {
        "name": "Priority Health",
        "url": "https://www.priorityhealth.com/provider",
        "folder": "Carrier Portals",
        "enabled": True,
    },
    {
        "name": "Molina",
        "url": "https://provider.molinahealthcare.com/",
        "folder": "Carrier Portals",
        "enabled": True,
    },
    {
        "name": "BCBS",
        "url": "https://www.bcbs.com/",
        "folder": "Carrier Portals",
        "enabled": True,
    },
    {
        "name": "Aetna",
        "url": "https://www.aetna.com/health-care-professionals.html",
        "folder": "Carrier Portals",
        "enabled": True,
    },
]
BILL_DEFAULT_BOOKMARK_FOLDERS = ["Bill Core", "TrackVia", "HealthSherpa", "CRM", "Carrier Portals"]
BILL_BOOKMARKS: list[dict[str, Any]] = [dict(item) for item in DEFAULT_BILL_BOOKMARKS]

DEFAULT_CONFIG = {
    "core_url": DEFAULT_CORE_URL,
    "fallback_core_urls": [],
    "worker_name": socket.gethostname(),
    "visible_mode": True,
    "auto_update_enabled": True,
    "poll_interval_seconds": 5,
    "log_level": "INFO",
    "worker_shared_secret": "",
    "prefer_system_chrome": PREFER_SYSTEM_CHROME,
    "bill_chrome_profile_dir": str(BILL_CHROME_PROFILE_DIR),
    "bill_bookmarks": [dict(item) for item in DEFAULT_BILL_BOOKMARKS],
    "chrome_profile_directory": CHROME_PROFILE_DIRECTORY,
    "remote_debugging_port": REMOTE_DEBUGGING_PORT,
    "browser_profile_policy": BROWSER_PROFILE_POLICY,
}


class MultiWriter:
    def __init__(self, *writers: Any):
        self._writers = [writer for writer in writers if writer is not None]

    def write(self, message: str) -> None:
        for writer in self._writers:
            writer.write(message)

    def flush(self) -> None:
        for writer in self._writers:
            writer.flush()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_info(message: str) -> None:
    print(f"{_timestamp()} [INFO] {message}")


def log_warn(message: str) -> None:
    print(f"{_timestamp()} [WARN] {message}")


def log_error(message: str) -> None:
    print(f"{_timestamp()} [ERROR] {message}")


@dataclass
class CoreConnectivityTracker:
    max_backoff_seconds: float = 60.0
    max_exponential_failures: int = 10
    failure_count: int = 0
    degraded: bool = False
    current_backoff_seconds: float = 0.0
    next_retry_at: float = 0.0
    degraded_since: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def _compute_backoff(self, failure_count: int) -> float:
        # Exponential backoff with a hard cap so retries never stop completely.
        effective_failures = min(max(0, int(failure_count)), max(0, int(self.max_exponential_failures)))
        exponential_backoff = float(2 ** max(0, effective_failures - 1))
        return max(0.0, min(float(self.max_backoff_seconds), exponential_backoff))

    def note_failure(self, operation: str, error: Exception) -> float:
        now = time.time()
        with self.lock:
            self.failure_count += 1
            self.current_backoff_seconds = self._compute_backoff(self.failure_count)
            max_jitter_by_ratio = min(1.0, self.current_backoff_seconds * 0.2)
            max_jitter_by_cap = max(0.0, float(self.max_backoff_seconds) - self.current_backoff_seconds)
            jitter = random.uniform(0.0, min(max_jitter_by_ratio, max_jitter_by_cap))
            self.next_retry_at = now + self.current_backoff_seconds + jitter

            if self.failure_count == 1:
                log_warn(
                    f"WORKER_CORE_REQUEST_FAILED operation={operation} "
                    f"error={error.__class__.__name__} backoff_seconds={self.current_backoff_seconds:.1f}"
                )

            if self.failure_count >= 2 and not self.degraded:
                self.degraded = True
                self.degraded_since = now
                log_warn(
                    f"WORKER_CORE_UNREACHABLE operation={operation} "
                    f"failure_count={self.failure_count} backoff_seconds={self.current_backoff_seconds:.1f}"
                )
            elif self.degraded:
                log_warn(
                    f"WORKER_CORE_UNREACHABLE operation={operation} "
                    f"failure_count={self.failure_count} backoff_seconds={self.current_backoff_seconds:.1f}"
                )

            return max(0.0, self.next_retry_at - now)

    def note_success(self, operation: str) -> None:
        now = time.time()
        with self.lock:
            if self.degraded:
                outage_seconds = 0.0
                if self.degraded_since is not None:
                    outage_seconds = max(0.0, now - self.degraded_since)
                log_info(
                    f"WORKER_CORE_RECOVERED operation={operation} "
                    f"outage_seconds={outage_seconds:.1f} previous_failure_count={self.failure_count}"
                )
            self.failure_count = 0
            self.degraded = False
            self.current_backoff_seconds = 0.0
            self.next_retry_at = 0.0
            self.degraded_since = None

    def seconds_until_next_attempt(self) -> float:
        with self.lock:
            if self.next_retry_at <= 0:
                return 0.0
            return max(0.0, self.next_retry_at - time.time())

    def current_backoff(self) -> float:
        with self.lock:
            return max(0.0, self.current_backoff_seconds)


CORE_CONNECTIVITY = CoreConnectivityTracker(max_backoff_seconds=60.0)
LAST_RUNTIME_SNAPSHOT: dict[str, Any] = {}
LAST_MACHINE_UUID: str | None = None


def _core_auth_headers(headers: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(headers or {})
    if WORKER_SHARED_SECRET:
        merged["X-Bill-Worker-Key"] = WORKER_SHARED_SECRET
    return merged


def _core_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    existing_headers = kwargs.pop("headers", None)
    kwargs["headers"] = _core_auth_headers(dict(existing_headers or {}))
    return requests.request(method, url, **kwargs)


def _truncate_text(value: str, max_len: int = 700) -> str:
    text = str(value or "")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "...<truncated>"


def _request_body_snippet(response: requests.Response | None) -> str:
    if response is None:
        return ""
    try:
        return _truncate_text(response.text.strip())
    except Exception:
        return "<unable to read response body>"


def _looks_like_html(response: requests.Response | None) -> bool:
    if response is None:
        return False
    content_type = str(response.headers.get("content-type") or "").lower()
    if "text/html" in content_type:
        return True
    snippet = _request_body_snippet(response).lower()
    return snippet.startswith("<!doctype html") or snippet.startswith("<html")


def _log_http_start(name: str, url: str, *, timeout: int, params: dict[str, Any] | None = None) -> None:
    if params:
        log_info(f"HTTP {name} request: url={url} timeout={timeout}s params={params}")
        return
    log_info(f"HTTP {name} request: url={url} timeout={timeout}s")


def _log_http_failure(name: str, url: str, error: Exception) -> None:
    CORE_CONNECTIVITY.note_failure(name, error)
    if isinstance(error, requests.exceptions.SSLError):
        log_error(f"HTTP {name} TLS/SSL failure: url={url} error={error!r}")
        return

    if isinstance(error, requests.RequestException):
        response = getattr(error, "response", None)
        if response is not None:
            snippet = _request_body_snippet(response)
            log_error(
                f"HTTP {name} failed: url={url} status={response.status_code} "
                f"content_type={response.headers.get('content-type')} body={snippet!r}"
            )
            if _looks_like_html(response):
                log_error(f"HTTP {name} expected JSON but received HTML from {url}")
            return
    log_error(f"HTTP {name} failed: url={url} error={error!r}")


def _log_non_json_response(name: str, url: str, response: requests.Response) -> None:
    snippet = _request_body_snippet(response)
    log_error(
        f"HTTP {name} returned non-JSON payload: url={url} status={response.status_code} "
        f"content_type={response.headers.get('content-type')} body={snippet!r}"
    )
    if _looks_like_html(response):
        log_error(f"HTTP {name} expected JSON but received HTML from {url}")


def initialize_logging() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"startup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    file_handle = open(log_path, "a", encoding="utf-8", buffering=1)
    sys.stdout = MultiWriter(sys.__stdout__, file_handle)
    sys.stderr = MultiWriter(sys.__stderr__, file_handle)
    return log_path


def _detect_chrome_path_for_startup() -> Path | None:
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _detect_system_chrome_path() -> Path | None:
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    return None


def _detect_debug_browser_path() -> Path | None:
    # Prefer system Chrome for visible/debug flows, but allow Edge fallback.
    chrome = _detect_system_chrome_path()
    if chrome is not None:
        return chrome

    edge_candidates = [
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in edge_candidates:
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _resolve_playwright_chromium_executable() -> str | None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright_context:
            return playwright_context.chromium.executable_path
    except Exception as exc:
        log_warn(f"[playwright-check] Could not resolve Chromium path: {exc}")
        return None


def _configure_playwright_browsers_path() -> str:
    configured = str(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if configured:
        return configured

    candidates = [
        APP_ROOT / "playwright-browsers",
        Path.home() / "AppData" / "Local" / "ms-playwright",
    ]
    for candidate in candidates:
        if candidate.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(candidate)
            return str(candidate)

    return "(default)"


def _attempt_playwright_install_chromium(timeout_seconds: int) -> None:
    started = time.monotonic()
    log_info(
        f"[playwright-check] install started: command='{sys.executable} -m playwright install chromium' timeout={timeout_seconds}s"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        duration = time.monotonic() - started
        if result.returncode == 0:
            log_info(f"[playwright-check] install succeeded: duration={duration:.1f}s")
            return

        log_warn(f"[playwright-check] install failed: exit_code={result.returncode} duration={duration:.1f}s")
        if result.stderr:
            log_warn(f"[playwright-check] install stderr: {result.stderr[:600]}")
        if result.stdout:
            log_info(f"[playwright-check] install stdout: {result.stdout[:300]}")
    except Exception as exc:
        duration = time.monotonic() - started
        log_warn(f"[playwright-check] install failed: duration={duration:.1f}s exception={exc!r}")


def _is_windows_interactive_session() -> bool:
    if os.name != "nt":
        return False
    try:
        stdin_tty = bool(sys.stdin and sys.stdin.isatty())
        stdout_tty = bool(sys.stdout and sys.stdout.isatty())
        return stdin_tty and stdout_tty
    except Exception:
        return False


def _playwright_status_for_startup() -> str:
    try:
        version = importlib_metadata.version("playwright")
        return f"available (version={version})"
    except Exception:
        return "not installed"


def _log_startup_environment(runtime_settings: dict[str, Any] | None = None) -> None:
    log_info(f"Startup CWD: {Path.cwd()}")
    log_info(f"Python/exe path: {sys.executable}")
    log_info(f"Frozen executable: {getattr(sys, 'frozen', False)}")
    log_info(f"Python version: {sys.version.split()[0]}")
    log_info(f"Platform: {platform.platform()}")
    log_info(f"PyInstaller _MEIPASS: {getattr(sys, '_MEIPASS', '(not set)')}")
    log_info(f"Config path: {CONFIG_PATH}")
    log_info(f"Config exists: {CONFIG_PATH.exists()}")
    log_info(f"Legacy config path: {LEGACY_CONFIG_PATH}")
    log_info(f"Legacy config exists: {LEGACY_CONFIG_PATH.exists()}")

    chrome_path = _detect_chrome_path_for_startup()
    if chrome_path is None:
        log_warn("Chrome path detected: none")
    else:
        log_info(f"Chrome path detected: {chrome_path}")

    log_info(f"Playwright availability: {_playwright_status_for_startup()}")

    if runtime_settings is not None:
        log_info(f"visible_mode value: {runtime_settings.get('visible_mode')}")
        log_info(f"core_url value: {runtime_settings.get('core_url')}")
        log_info(f"worker_name value: {runtime_settings.get('worker_name')}")
        log_info(f"worker_secret_present: {runtime_settings.get('worker_secret_present')}")
        log_info(f"worker_secret_source: {runtime_settings.get('worker_secret_source')}")


def _write_fatal_startup_log(error: Exception, traceback_text: str) -> Path | None:
    candidates = [Path.home() / "Desktop" / "bill-worker-startup-fatal.log", LOGS_DIR / "startup_fatal.log"]
    for log_path in candidates:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("\n")
                handle.write(f"===== {datetime.now().isoformat()} =====\n")
                handle.write(f"Fatal startup error: {error!r}\n")
                handle.write(f"Startup CWD: {Path.cwd()}\n")
                handle.write(f"Python/exe path: {sys.executable}\n")
                handle.write(f"Config path: {CONFIG_PATH}\n")
                handle.write(f"Config exists: {CONFIG_PATH.exists()}\n")
                handle.write(f"worker_secret_present: {bool(WORKER_SHARED_SECRET)}\n")
                handle.write(f"visible_mode value: {DEFAULT_WORKER_MODE}\n")
                handle.write(f"core_url value: {API_BASE}\n")
                handle.write(f"worker_name value: {MACHINE_DISPLAY_NAME_OVERRIDE or socket.gethostname()}\n")
                chrome_path = _detect_chrome_path_for_startup()
                handle.write(f"Chrome path detected: {chrome_path if chrome_path else 'none'}\n")
                handle.write(f"Playwright availability: {_playwright_status_for_startup()}\n")
                handle.write(traceback_text)
                if not traceback_text.endswith("\n"):
                    handle.write("\n")
            return log_path
        except Exception:
            continue
    return None


def _write_startup_error_log(error: Exception, traceback_text: str) -> Path | None:
    candidates = [APP_ROOT / "startup_error.log", LOGS_DIR / "startup_error.log"]
    for log_path in candidates:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write("\n")
                handle.write(f"===== {datetime.now().isoformat()} =====\n")
                handle.write(f"Startup failure: {error!r}\n")
                handle.write(f"App root: {APP_ROOT}\n")
                handle.write(f"Startup CWD: {Path.cwd()}\n")
                handle.write(f"Python/exe path: {sys.executable}\n")
                handle.write(f"Frozen executable: {getattr(sys, 'frozen', False)}\n")
                handle.write(f"Python version: {sys.version.split()[0]}\n")
                handle.write(f"Platform: {platform.platform()}\n")
                handle.write(f"PyInstaller _MEIPASS: {getattr(sys, '_MEIPASS', '(not set)')}\n")
                handle.write(f"Config path searched: {CONFIG_PATH}\n")
                handle.write(f"Config loaded: {CONFIG_PATH.exists()}\n")
                handle.write(f"Core URL: {API_BASE}\n")
                handle.write(f"worker_secret_present: {bool(WORKER_SHARED_SECRET)}\n")
                chrome_path = _detect_chrome_path_for_startup()
                handle.write(f"Chrome path detected: {chrome_path if chrome_path else 'none'}\n")
                handle.write(f"Playwright available: {_playwright_status_for_startup()}\n")
                handle.write(traceback_text)
                if not traceback_text.endswith("\n"):
                    handle.write("\n")
            return log_path
        except Exception:
            continue
    return None


def _show_startup_error_message_box() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Bill Worker failed to start. See logs/startup_error.log.",
            "Bill Worker Startup Error",
            0x10,
        )
    except Exception:
        return


@dataclass
class RuntimeState:
    connected: bool = False
    status: str = "idle"
    execution_mode: str = "headless_background"
    current_task_id: str | None = None
    current_step: str | None = None
    last_error: str | None = None
    browser_profile_policy: str = "bill_profile"
    bill_profile_ready: bool = False
    bookmarks_ready: bool = False
    debug_port_ready: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "connected": self.connected,
                "status": self.status,
                "execution_mode": self.execution_mode,
                "current_task_id": self.current_task_id,
                "current_step": self.current_step,
                "last_error": self.last_error,
                "browser_profile_policy": self.browser_profile_policy,
                "bill_profile_ready": self.bill_profile_ready,
                "bookmarks_ready": self.bookmarks_ready,
                "debug_port_ready": self.debug_port_ready,
            }

    def is_busy(self) -> bool:
        with self.lock:
            return self.status == "busy"

    def set_connected(self, connected: bool) -> None:
        with self.lock:
            self.connected = connected

    def set_busy(self, task_id: str | None, mode: str, step: str | None = None) -> None:
        with self.lock:
            self.status = "busy"
            self.execution_mode = mode
            self.current_task_id = task_id
            self.current_step = step
            self.last_error = None

    def set_browser_profile_status(
        self,
        policy: str,
        bill_profile_ready: bool,
        bookmarks_ready: bool,
        debug_port_ready: bool,
    ) -> None:
        with self.lock:
            self.browser_profile_policy = str(policy or "bill_profile")
            self.bill_profile_ready = bool(bill_profile_ready)
            self.bookmarks_ready = bool(bookmarks_ready)
            self.debug_port_ready = bool(debug_port_ready)

    def set_step(self, step: str | None) -> None:
        with self.lock:
            self.current_step = step

    def set_idle(self, mode: str | None = None) -> None:
        with self.lock:
            self.status = "idle"
            if mode:
                self.execution_mode = mode
            self.current_task_id = None
            self.current_step = None

    def set_error(self, error_message: str, mode: str | None = None) -> None:
        with self.lock:
            self.status = "error"
            if mode:
                self.execution_mode = mode
            self.last_error = error_message


def _get_setting(config: dict[str, Any], config_key: str, env_keys: list[str], default: Any) -> Any:
    for env_key in env_keys:
        env_value = os.getenv(env_key)
        if env_value is not None and env_value != "":
            return env_value
    if config_key in config:
        return config.get(config_key)
    return default


def _parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _parse_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _resolve_dir(value: Any, fallback: Path, worker_root: Path) -> Path:
    if not value:
        return fallback
    candidate = Path(str(value))
    if not candidate.is_absolute():
        candidate = (worker_root / candidate).resolve()
    return candidate


def _normalize_bill_bookmarks(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return [dict(item) for item in DEFAULT_BILL_BOOKMARKS]

    normalized: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        url = str(item.get("url") or "").strip()
        folder = str(item.get("folder") or "").strip() or "Bill Core"
        enabled = _parse_bool(item.get("enabled"), True)
        if not name or not url:
            continue
        if not url.startswith(("http://", "https://")):
            continue
        normalized.append(
            {
                "name": name,
                "url": url,
                "folder": folder,
                "enabled": enabled,
            }
        )

    if not normalized:
        return [dict(item) for item in DEFAULT_BILL_BOOKMARKS]
    return normalized


def _resolve_bill_chrome_profile_dir(value: Any) -> Path:
    fallback = BILL_CHROME_PROFILE_DIR
    if not value:
        return fallback
    raw = str(value).strip()
    if not raw:
        return fallback
    expanded = os.path.expandvars(raw)
    path = Path(expanded)
    if not path.is_absolute():
        path = (APP_ROOT / path).resolve()
    return path


def load_worker_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        if LEGACY_CONFIG_PATH.exists():
            try:
                legacy = json.loads(LEGACY_CONFIG_PATH.read_text(encoding="utf-8-sig"))
                if isinstance(legacy, dict):
                    migrated = {
                        "core_url": legacy.get("core_url", DEFAULT_CONFIG["core_url"]),
                        "worker_name": legacy.get("machine_display_name", DEFAULT_CONFIG["worker_name"]),
                        "visible_mode": str(legacy.get("default_execution_mode", "interactive_visible")).strip() == "interactive_visible",
                        "poll_interval_seconds": legacy.get("polling_interval_seconds", DEFAULT_CONFIG["poll_interval_seconds"]),
                        "log_level": DEFAULT_CONFIG["log_level"],
                        "bill_chrome_profile_dir": DEFAULT_CONFIG["bill_chrome_profile_dir"],
                        "bill_bookmarks": [dict(item) for item in DEFAULT_BILL_BOOKMARKS],
                        "chrome_profile_directory": DEFAULT_CONFIG["chrome_profile_directory"],
                        "remote_debugging_port": DEFAULT_CONFIG["remote_debugging_port"],
                        "browser_profile_policy": DEFAULT_CONFIG["browser_profile_policy"],
                    }
                    CONFIG_PATH.write_text(json.dumps(migrated, indent=2), encoding="utf-8")
                    log_info(f"Migrated legacy config to {CONFIG_PATH}")
            except Exception as error:
                log_warn(f"Unable to migrate legacy config: {error}")

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        log_warn(f"config.json not found. Created default config at {CONFIG_PATH}")

    if not CONFIG_PATH.exists():
        return {}

    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except Exception as error:
        raise ValueError(f"Failed to parse config.json: {error}") from error

    if not isinstance(config, dict):
        raise ValueError("config.json must contain a JSON object")

    merged = dict(DEFAULT_CONFIG)
    merged.update(config)

    core_url = str(merged.get("core_url", "")).strip()
    if not core_url:
        raise ValueError("config.json validation failed: 'core_url' must be non-empty")
    if not (core_url.startswith("http://") or core_url.startswith("https://")):
        raise ValueError("config.json validation failed: 'core_url' must start with http:// or https://")

    worker_name = str(merged.get("worker_name", "")).strip()
    if not worker_name:
        raise ValueError("config.json validation failed: 'worker_name' must be non-empty")

    merged["core_url"] = core_url
    merged["worker_name"] = worker_name
    merged["visible_mode"] = _parse_bool(merged.get("visible_mode"), True)
    merged["poll_interval_seconds"] = max(1.0, _parse_float(merged.get("poll_interval_seconds"), 5.0))
    merged["log_level"] = str(merged.get("log_level", "INFO")).upper()
    if merged["log_level"] not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        merged["log_level"] = "INFO"
    merged["bill_chrome_profile_dir"] = str(_resolve_bill_chrome_profile_dir(merged.get("bill_chrome_profile_dir")))
    merged["bill_bookmarks"] = _normalize_bill_bookmarks(merged.get("bill_bookmarks"))
    merged["chrome_profile_directory"] = str(merged.get("chrome_profile_directory") or "Default").strip() or "Default"
    merged["remote_debugging_port"] = max(1, int(_parse_float(merged.get("remote_debugging_port"), 9222)))
    browser_policy = str(merged.get("browser_profile_policy") or "bill_profile").strip().lower()
    if browser_policy not in {"bill_profile", "isolated_temp_profile", "attach_existing_debug"}:
        browser_policy = "bill_profile"
    merged["browser_profile_policy"] = browser_policy

    return merged


# ---------------------------------------------------------------------------
# Core URL health preflight + fallback selection
# ---------------------------------------------------------------------------

def _check_core_url_health(url: str) -> tuple[bool, str]:
    """Probe <url>/health.  Returns (is_healthy, reason_string)."""
    health_url = url.rstrip("/") + "/health"
    try:
        resp = requests.get(health_url, timeout=8)
        body = resp.text or ""
        # Cloudflare Tunnel hard-error (HTTP 530 or recognisable HTML body)
        if resp.status_code == 530:
            return False, f"CLOUDFLARE_TUNNEL_ERROR detected (HTTP 530) for {url}"
        if "Cloudflare Tunnel error" in body or (
            "cloudflare" in body.lower() and "error" in body.lower()
        ):
            return False, f"CLOUDFLARE_TUNNEL_ERROR detected (Cloudflare HTML body) for {url}"
        if not resp.ok:
            return False, f"HTTP {resp.status_code} from {health_url}"
        try:
            data = resp.json()
        except Exception:
            return False, f"Non-JSON response from {health_url} (received HTML or plain text)"
        status = str(data.get("status", "")).lower()
        if status in ("ok", "healthy", ""):
            return True, "ok"
        return False, f"Unexpected health status value: {data.get('status')!r}"
    except requests.exceptions.ConnectionError as exc:
        return False, f"Connection error reaching {health_url}: {exc}"
    except requests.exceptions.Timeout:
        return False, f"Timeout (8 s) connecting to {health_url}"
    except Exception as exc:
        return False, f"Unexpected error probing {health_url}: {exc}"


def _select_active_core_url(primary: str, fallbacks: list[str]) -> str:
    """
    Try primary URL /health, then each fallback in order.
    Returns the first URL that responds with a healthy JSON payload.
    If all fail, returns primary (worker will surface errors at register time).
    """
    candidates = [primary] + [u.rstrip("/") for u in fallbacks if u]
    for url in candidates:
        url = url.rstrip("/")
        log_info(f"[core-url-select] Probing {url}/health ...")
        healthy, reason = _check_core_url_health(url)
        if healthy:
            if url == primary:
                log_info(f"CORE_URL_SELECTED url={url} (primary)")
            else:
                log_warn(
                    f"CORE_URL_SELECTED url={url} (fallback — primary {primary} was unreachable)"
                )
            return url
        # Log the failure with appropriate severity
        if "CLOUDFLARE_TUNNEL_ERROR" in reason:
            log_warn(f"{reason}. Trying fallback.")
        else:
            log_warn(f"Bill Core API is unreachable at {url}: {reason}")

    # All candidates failed
    tried = ", ".join(candidates)
    log_warn(
        f"Bill Worker cannot reach Bill Core. "
        f"Check backend deployment, Cloudflare tunnel, or core_url in config.json. "
        f"Tried: {tried}"
    )
    return primary  # best-effort: continue with primary so later errors are surfaced normally


def apply_runtime_config() -> dict[str, Any]:
    global API_BASE
    global HEARTBEAT_INTERVAL_SECONDS
    global POLLING_INTERVAL_SECONDS
    global UPDATE_CHECK_INTERVAL_SECONDS
    global AUTO_UPDATE_ENABLED
    global MACHINE_DISPLAY_NAME_OVERRIDE
    global DEFAULT_WORKER_MODE
    global WORKER_UI_ENABLED
    global LOG_LEVEL
    global PREFER_SYSTEM_CHROME
    global BILL_CHROME_PROFILE_DIR
    global BILL_BOOKMARKS
    global CHROME_PROFILE_DIRECTORY
    global REMOTE_DEBUGGING_PORT
    global BROWSER_PROFILE_POLICY
    global WORKER_SHARED_SECRET

    config = load_worker_config()

    API_BASE = str(_get_setting(config, "core_url", ["BILL_CORE_URL", "JARVIS_CORE_URL"], DEFAULT_CORE_URL)).rstrip("/")

    # Health preflight: try primary then any fallback_core_urls from config
    raw_fallbacks = config.get("fallback_core_urls") or []
    fallback_urls: list[str] = (
        [str(u).rstrip("/") for u in raw_fallbacks if u]
        if isinstance(raw_fallbacks, list)
        else []
    )
    API_BASE = _select_active_core_url(API_BASE, fallback_urls)

    MACHINE_DISPLAY_NAME_OVERRIDE = str(
        _get_setting(config, "worker_name", ["BILL_WORKER_MACHINE_NAME", "JARVIS_WORKER_MACHINE_NAME"], socket.gethostname())
    ).strip()

    visible_mode = _parse_bool(_get_setting(config, "visible_mode", [], True), True)
    AUTO_UPDATE_ENABLED = _parse_bool(_get_setting(config, "auto_update_enabled", [], True), True)
    DEFAULT_WORKER_MODE = "interactive_visible" if visible_mode else "headless_background"

    POLLING_INTERVAL_SECONDS = max(1.0, _parse_float(_get_setting(config, "poll_interval_seconds", [], 5), 5.0))
    HEARTBEAT_INTERVAL_SECONDS = max(5.0, POLLING_INTERVAL_SECONDS)
    UPDATE_CHECK_INTERVAL_SECONDS = max(30.0, _parse_float(_get_setting(config, "update_check_interval_seconds", [], 120), 120.0))

    LOG_LEVEL = str(_get_setting(config, "log_level", [], "INFO")).upper()
    if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        LOG_LEVEL = "INFO"

    PREFER_SYSTEM_CHROME = _parse_bool(
        _get_setting(
            config,
            "prefer_system_chrome",
            ["BILL_WORKER_PREFER_SYSTEM_CHROME", "JARVIS_WORKER_PREFER_SYSTEM_CHROME"],
            bool(getattr(sys, "frozen", False)),
        ),
        bool(getattr(sys, "frozen", False)),
    )
    BILL_CHROME_PROFILE_DIR = _resolve_bill_chrome_profile_dir(
        _get_setting(
            config,
            "bill_chrome_profile_dir",
            ["BILL_WORKER_CHROME_PROFILE_DIR", "JARVIS_WORKER_CHROME_PROFILE_DIR"],
            str(BILL_CHROME_PROFILE_DIR),
        )
    )
    BILL_BOOKMARKS = _normalize_bill_bookmarks(config.get("bill_bookmarks"))
    CHROME_PROFILE_DIRECTORY = str(
        _get_setting(
            config,
            "chrome_profile_directory",
            ["BILL_WORKER_CHROME_PROFILE_DIRECTORY", "JARVIS_WORKER_CHROME_PROFILE_DIRECTORY"],
            "Default",
        )
    ).strip() or "Default"
    REMOTE_DEBUGGING_PORT = max(
        1,
        int(
            _parse_float(
                _get_setting(
                    config,
                    "remote_debugging_port",
                    ["BILL_WORKER_REMOTE_DEBUGGING_PORT", "JARVIS_WORKER_REMOTE_DEBUGGING_PORT"],
                    9222,
                ),
                9222,
            )
        ),
    )
    configured_policy = str(
        _get_setting(
            config,
            "browser_profile_policy",
            ["BILL_WORKER_BROWSER_PROFILE_POLICY", "JARVIS_WORKER_BROWSER_PROFILE_POLICY"],
            "bill_profile",
        )
    ).strip().lower()
    if configured_policy not in {"bill_profile", "isolated_temp_profile", "attach_existing_debug"}:
        configured_policy = "bill_profile"
    BROWSER_PROFILE_POLICY = configured_policy

    WORKER_UI_ENABLED = True

    WORKER_SHARED_SECRET, worker_secret_source = _resolve_worker_shared_secret(config)
    if not WORKER_SHARED_SECRET:
        log_warn("Worker shared secret missing. Set BILL_CORE_WORKER_SHARED_SECRET or worker_shared_secret in config.json.")

    screenshots_dir = _resolve_dir(str(SCREENSHOTS_DIR), SCREENSHOTS_DIR, APP_ROOT)
    downloads_dir = _resolve_dir(str(DOWNLOADS_DIR), DOWNLOADS_DIR, APP_ROOT)

    screenshots_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    BILL_CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["BILL_CORE_URL"] = API_BASE
    os.environ["JARVIS_CORE_URL"] = API_BASE
    os.environ["BILL_WORKER_DEFAULT_MODE"] = DEFAULT_WORKER_MODE
    os.environ["JARVIS_WORKER_DEFAULT_MODE"] = DEFAULT_WORKER_MODE
    os.environ["BILL_WORKER_SCREENSHOTS_DIR"] = str(screenshots_dir)
    os.environ["JARVIS_WORKER_SCREENSHOTS_DIR"] = str(screenshots_dir)
    os.environ["BILL_WORKER_DOWNLOADS_DIR"] = str(downloads_dir)
    os.environ["JARVIS_WORKER_DOWNLOADS_DIR"] = str(downloads_dir)
    os.environ["BILL_WORKER_HEARTBEAT_INTERVAL"] = str(HEARTBEAT_INTERVAL_SECONDS)
    os.environ["JARVIS_WORKER_HEARTBEAT_INTERVAL"] = str(HEARTBEAT_INTERVAL_SECONDS)
    os.environ["BILL_WORKER_POLLING_INTERVAL"] = str(POLLING_INTERVAL_SECONDS)
    os.environ["JARVIS_WORKER_POLLING_INTERVAL"] = str(POLLING_INTERVAL_SECONDS)
    os.environ["BILL_WORKER_UI"] = "1" if WORKER_UI_ENABLED else "0"
    os.environ["JARVIS_WORKER_UI"] = "1" if WORKER_UI_ENABLED else "0"
    os.environ["BILL_WORKER_PREFER_SYSTEM_CHROME"] = "1" if PREFER_SYSTEM_CHROME else "0"
    os.environ["JARVIS_WORKER_PREFER_SYSTEM_CHROME"] = "1" if PREFER_SYSTEM_CHROME else "0"
    os.environ["BILL_WORKER_CHROME_PROFILE_DIR"] = str(BILL_CHROME_PROFILE_DIR)
    os.environ["JARVIS_WORKER_CHROME_PROFILE_DIR"] = str(BILL_CHROME_PROFILE_DIR)
    os.environ["BILL_WORKER_CHROME_PROFILE_DIRECTORY"] = CHROME_PROFILE_DIRECTORY
    os.environ["JARVIS_WORKER_CHROME_PROFILE_DIRECTORY"] = CHROME_PROFILE_DIRECTORY
    os.environ["BILL_WORKER_REMOTE_DEBUGGING_PORT"] = str(REMOTE_DEBUGGING_PORT)
    os.environ["JARVIS_WORKER_REMOTE_DEBUGGING_PORT"] = str(REMOTE_DEBUGGING_PORT)
    os.environ["BILL_WORKER_BROWSER_PROFILE_POLICY"] = BROWSER_PROFILE_POLICY
    os.environ["JARVIS_WORKER_BROWSER_PROFILE_POLICY"] = BROWSER_PROFILE_POLICY
    os.environ["BILL_WORKER_BOOKMARKS_JSON"] = json.dumps(BILL_BOOKMARKS)
    os.environ["JARVIS_WORKER_BOOKMARKS_JSON"] = json.dumps(BILL_BOOKMARKS)
    if WORKER_SHARED_SECRET:
        os.environ["BILL_CORE_WORKER_SHARED_SECRET"] = WORKER_SHARED_SECRET

    return {
        "core_url": API_BASE,
        "worker_name": MACHINE_DISPLAY_NAME_OVERRIDE,
        "visible_mode": visible_mode,
        "auto_update_enabled": AUTO_UPDATE_ENABLED,
        "log_level": LOG_LEVEL,
        "default_execution_mode": DEFAULT_WORKER_MODE,
        "heartbeat_interval_seconds": HEARTBEAT_INTERVAL_SECONDS,
        "polling_interval_seconds": POLLING_INTERVAL_SECONDS,
        "update_check_interval_seconds": UPDATE_CHECK_INTERVAL_SECONDS,
        "screenshots_dir": str(screenshots_dir),
        "downloads_dir": str(downloads_dir),
        "show_local_ui": WORKER_UI_ENABLED,
        "prefer_system_chrome": PREFER_SYSTEM_CHROME,
        "bill_chrome_profile_dir": str(BILL_CHROME_PROFILE_DIR),
        "bill_bookmarks_count": len(BILL_BOOKMARKS),
        "chrome_profile_directory": CHROME_PROFILE_DIRECTORY,
        "remote_debugging_port": REMOTE_DEBUGGING_PORT,
        "browser_profile_policy": BROWSER_PROFILE_POLICY,
        "worker_secret_present": bool(WORKER_SHARED_SECRET),
        "worker_secret_source": worker_secret_source,
    }


def _normalize_mode(value: str | None, default: str) -> str:
    normalized = (value or default or "headless_background").strip()
    if normalized not in {"interactive_visible", "headless_background"}:
        return default
    return normalized


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8-sig"))
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        print(f"[worker] secret file not found at {SECRETS_PATH}; value_from_secret lookups will fail")
        return {}

    try:
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8-sig"))
    except Exception as error:
        print(f"[worker] failed to parse secrets file: {error}")
        return {}

    if not isinstance(data, dict):
        print("[worker] secrets file must contain a JSON object")
        return {}

    return {str(key): str(value) for key, value in data.items()}


def _resolve_worker_shared_secret(config: dict[str, Any]) -> tuple[str, str]:
    env_value = str(os.getenv("BILL_CORE_WORKER_SHARED_SECRET") or "").strip()
    if env_value:
        return env_value, "env:BILL_CORE_WORKER_SHARED_SECRET"

    config_value = str(config.get("worker_shared_secret") or "").strip()
    if config_value:
        return config_value, "config:worker_shared_secret"

    secrets = load_secrets()
    for key in ["BILL_CORE_WORKER_SHARED_SECRET", "worker_shared_secret"]:
        secret_value = str(secrets.get(key) or "").strip()
        if secret_value:
            return secret_value, f"secrets.local.json:{key}"

    return "", "missing"


def resolve_secret_value(secret_name: str, secrets: dict[str, str]) -> str:
    if secret_name not in secrets:
        raise ValueError(f"Secret '{secret_name}' not found in local secret config")
    return secrets[secret_name]


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw_part in str(version).strip().split("."):
        digits = "".join(ch for ch in raw_part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _is_newer_version(candidate: str, current: str) -> bool:
    return _version_key(candidate) > _version_key(current)


def _compute_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with open(file_path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _queue_pending_update(state: dict[str, Any], payload: dict[str, Any], source: str, reason: str) -> None:
    latest_version = str(payload.get("latest_version") or "").strip()
    package_url = str(payload.get("package_url") or "").strip()
    package_sha256 = str(payload.get("package_sha256") or "").strip().lower()

    state["update_pending"] = True
    state["pending_update_version"] = latest_version
    state["pending_update"] = {
        "update_available": True,
        "latest_version": latest_version,
        "package_url": package_url,
        "package_sha256": package_sha256,
        "source": source,
        "queued_reason": reason,
        "queued_at": datetime.utcnow().isoformat(),
        "retry_count": int((state.get("pending_update") or {}).get("retry_count") or 0),
    }
    save_state(state)


def _get_pending_update_payload(state: dict[str, Any]) -> dict[str, Any] | None:
    pending = state.get("pending_update")
    if isinstance(pending, dict):
        latest_version = str(pending.get("latest_version") or "").strip()
        package_url = str(pending.get("package_url") or "").strip()
        if latest_version and package_url:
            return {
                "update_available": True,
                "latest_version": latest_version,
                "package_url": package_url,
                "package_sha256": str(pending.get("package_sha256") or "").strip(),
            }

    pending_version = str(state.get("pending_update_version") or "").strip()
    if pending_version:
        # Legacy fallback state; we need a fresh check to get package URL.
        return None
    return None


def _download_update_package(package_url: str, destination_path: Path) -> None:
    parsed = urlparse(package_url)
    scheme = (parsed.scheme or "").lower()

    if scheme in {"", "file"}:
        local_path = parsed.path if scheme == "file" else package_url
        if scheme == "file" and os.name == "nt" and local_path.startswith("/") and len(local_path) > 2 and local_path[2] == ":":
            local_path = local_path[1:]
        source_path = Path(local_path)
        if not source_path.exists():
            raise FileNotFoundError(f"Update package not found: {source_path}")
        destination_path.write_bytes(source_path.read_bytes())
        return

    if scheme in {"http", "https"}:
        with _core_request("GET", package_url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with open(destination_path, "wb") as out_file:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        out_file.write(chunk)
        return

    raise ValueError(f"Unsupported update package URL scheme: {scheme}")


def _launch_windows_updater(package_path: Path, app_root: Path, executable_path: Path, updater_script_url: str | None = None) -> None:
    script_path = package_path.with_suffix(".update.ps1")
    script_content = """param(
  [Parameter(Mandatory=$true)][string]$PackagePath,
  [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$ExePath,
    [Parameter(Mandatory=$true)][int]$WorkerPid
)
$ErrorActionPreference = 'Stop'
$logPath = Join-Path ([IO.Path]::GetDirectoryName($PackagePath)) 'last_update.log'
function Write-UpdateLog([string]$Message) {
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $logPath -Value "[$timestamp] $Message"
}
function Invoke-RobocopySafe([string]$Source, [string]$Destination, [string[]]$ExtraArgs, [int]$FailThreshold = 8) {
    $args = @(
        $Source,
        $Destination,
        '/E',
        '/R:2',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NP'
    ) + $ExtraArgs

    $robo = Start-Process -FilePath 'robocopy.exe' -ArgumentList $args -NoNewWindow -Wait -PassThru
    $code = [int]($robo.ExitCode)
    Write-UpdateLog "Robocopy [$Source -> $Destination] exit code: $code"
    if ($code -ge $FailThreshold) {
        throw "Robocopy failed with exit code $code"
    }
}
Write-UpdateLog "Updater started. pid=$WorkerPid package=$PackagePath install=$InstallDir exe=$ExePath"

$extractRoot = $null
$backupRoot = $null

for ($i = 0; $i -lt 120; $i++) {
    $proc = Get-Process -Id $WorkerPid -ErrorAction SilentlyContinue
    if (-not $proc) { break }
    Start-Sleep -Milliseconds 500
}

$stillRunning = Get-Process -Id $WorkerPid -ErrorAction SilentlyContinue
if ($stillRunning) {
    Write-UpdateLog "Worker process still running after wait window. Continuing update copy anyway."
} else {
    Write-UpdateLog "Worker process has exited; proceeding with update copy."
}

try {
    $extractRoot = Join-Path ([IO.Path]::GetDirectoryName($PackagePath)) ("bill_worker_update_" + [guid]::NewGuid().ToString("N"))
    Expand-Archive -Path $PackagePath -DestinationPath $extractRoot -Force
    $children = Get-ChildItem -LiteralPath $extractRoot -Force
    $sourceRoot = $extractRoot
    if ($children.Count -eq 1 -and $children[0].PSIsContainer) {
      $sourceRoot = $children[0].FullName
    }

    $sourceExe = Join-Path $sourceRoot 'BillWorker.exe'
    if (-not (Test-Path $sourceExe)) {
        throw "Updated package does not contain BillWorker.exe at $sourceExe"
    }
    Write-UpdateLog "Extracted update package to: $sourceRoot"

    $backupRoot = Join-Path ([IO.Path]::GetDirectoryName($PackagePath)) ("bill_worker_backup_" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Write-UpdateLog "Creating rollback backup at: $backupRoot"
    # Use threshold 16 (fatal errors only) for backup - locked files (e.g. Chrome profile on Desktop) are acceptable
    Invoke-RobocopySafe -Source $InstallDir -Destination $backupRoot -FailThreshold 16 -ExtraArgs @(
        '/XF',
        'config.json',
        'worker-config.json',
        'secrets.local.json',
        '.worker_state.json',
        '/XD',
        'logs',
        'screenshots',
        'downloads',
        'updates'
    )

    Write-UpdateLog "Applying update files from $sourceRoot to $InstallDir"
    Invoke-RobocopySafe -Source $sourceRoot -Destination $InstallDir -ExtraArgs @(
        '/XF',
        'config.json',
        'worker-config.json',
        'secrets.local.json',
        '.worker_state.json',
        '/XD',
        'logs',
        'screenshots',
        'downloads'
    )

    $destExe = Join-Path $InstallDir 'BillWorker.exe'
    if (-not (Test-Path $destExe)) {
        throw "BillWorker.exe missing after copy at $destExe"
    }

    Start-Sleep -Seconds 1

    # Always restart via BillWorker.exe directly - start-bill-worker.cmd launches Python, not the exe
    $newExePath = Join-Path $InstallDir 'BillWorker.exe'
    $started = $false
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        try {
            Start-Process -FilePath $newExePath -WorkingDirectory $InstallDir
            Write-UpdateLog "Relaunch requested via BillWorker.exe at $newExePath (attempt $attempt)."
            $started = $true
            break
        } catch {
            Write-UpdateLog "Relaunch attempt $attempt failed: $($_.Exception.Message)"
            Start-Sleep -Seconds 2
        }
    }

    if (-not $started) {
        Write-UpdateLog "WARNING: All relaunch attempts failed. Update files are in place; please restart BillWorker manually."
    } else {
        $up = $false
        for ($i = 0; $i -lt 30; $i++) {
            $running = Get-Process -Name 'BillWorker' -ErrorAction SilentlyContinue
            if ($running) {
                $up = $true
                break
            }
            Start-Sleep -Seconds 1
        }

        if (-not $up) {
            Write-UpdateLog "WARNING: BillWorker process not detected within 30s. Update files are in place; please restart BillWorker manually."
        } else {
            Write-UpdateLog "BillWorker process confirmed running after update."
        }
    }

    Write-UpdateLog "Updater completed successfully."
} catch {
    Write-UpdateLog "Update failed: $($_.Exception.Message)"
    # Only rollback on file copy failures, not on restart detection failures
    if ($backupRoot -and (Test-Path $backupRoot) -and (-not (Test-Path (Join-Path $InstallDir 'BillWorker.exe')))) {
        try {
            Write-UpdateLog "Attempting rollback from backup: $backupRoot"
            Invoke-RobocopySafe -Source $backupRoot -Destination $InstallDir -ExtraArgs @(
                '/XF',
                'config.json',
                'worker-config.json',
                'secrets.local.json',
                '.worker_state.json',
                '/XD',
                'logs',
                'screenshots',
                'downloads',
                'updates'
            )
            Write-UpdateLog "Rollback completed successfully."
        } catch {
            Write-UpdateLog "Rollback failed: $($_.Exception.Message)"
        }
    }
    throw
} finally {
    if ($extractRoot -and (Test-Path $extractRoot)) {
        try { Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($backupRoot -and (Test-Path $backupRoot)) {
        try { Remove-Item -LiteralPath $backupRoot -Recurse -Force -ErrorAction SilentlyContinue } catch {}
    }
}
"""
    # Try to download the latest PS1 from the server so any exe version gets the fixed script
    script_downloaded = False
    if updater_script_url:
        try:
            resp = _core_request("GET", updater_script_url, timeout=15)
            resp.raise_for_status()
            script_path.write_text(resp.text, encoding="utf-8")
            script_downloaded = True
            log_info(f"Worker updater: downloaded PS1 script from {updater_script_url}")
        except Exception as dl_err:
            log_warn(f"Worker updater: failed to download PS1 from {updater_script_url}: {dl_err}; using embedded script")
    if not script_downloaded:
        script_path.write_text(script_content, encoding="utf-8")

    creation_flags = 0
    creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    powershell_exe = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    if not os.path.exists(powershell_exe):
        powershell_exe = "powershell"

    subprocess.Popen(
        [
            powershell_exe,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-PackagePath",
            str(package_path),
            "-InstallDir",
            str(app_root),
            "-ExePath",
            str(executable_path),
            "-WorkerPid",
            str(os.getpid()),
        ],
        cwd=str(app_root),
        creationflags=creation_flags,
    )


def _launch_restart_watchdog(app_root: Path, delay_seconds: int = 20) -> None:
    # Try the known launcher names in order
    start_bat = app_root / "start-bill-worker.cmd"
    if not start_bat.exists():
        start_bat = app_root / "start_worker.bat"
    if not start_bat.exists():
        return

    powershell_exe = os.path.join(
        os.environ.get("WINDIR", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    if not os.path.exists(powershell_exe):
        powershell_exe = "powershell"

    creation_flags = 0
    creation_flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    creation_flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    safe_start_bat = str(start_bat).replace("'", "''")
    safe_working_dir = str(app_root).replace("'", "''")
    cmd = (
        f"Start-Sleep -Seconds {max(10, int(delay_seconds))}; "
        f"Start-Process -FilePath '{safe_start_bat}' -WorkingDirectory '{safe_working_dir}'"
    )

    subprocess.Popen(
        [
            powershell_exe,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            cmd,
        ],
        cwd=str(app_root),
        creationflags=creation_flags,
    )


def _apply_update_payload(
    payload: dict[str, Any],
    state: dict[str, Any],
    source: str,
    runtime_state: RuntimeState | None = None,
    allow_pending_retry: bool = False,
) -> bool:
    if not AUTO_UPDATE_ENABLED:
        return False

    if not getattr(sys, "frozen", False):
        log_info("Auto-update check skipped (non-frozen/dev worker runtime).")
        return False

    if not isinstance(payload, dict):
        return False

    update_available = bool(payload.get("update_available"))
    latest_version = str(payload.get("latest_version") or "").strip()
    package_url = str(payload.get("package_url") or "").strip()
    package_sha256 = str(payload.get("package_sha256") or "").strip().lower()
    updater_script_url = str(payload.get("updater_script_url") or "").strip() or None

    if not update_available or not latest_version or not package_url:
        log_info(f"Worker auto-update ({source}): no update required.")
        return False

    if not _is_newer_version(latest_version, WORKER_VERSION):
        log_info(f"Worker auto-update ({source}): core returned non-newer version, skipping.")
        return False

    pending_version = str(state.get("pending_update_version") or "").strip()
    if pending_version and pending_version == latest_version and not allow_pending_retry:
        log_warn(
            f"Worker auto-update ({source}): pending_update_version already set to {latest_version}; skipping duplicate apply attempt."
        )
        return False

    if runtime_state is not None and runtime_state.is_busy():
        log_warn(
            f"Worker auto-update ({source}): update detected but worker is busy; queuing pending update to {latest_version}."
        )
        _queue_pending_update(state, payload, source=source, reason="worker_busy")
        return False

    if allow_pending_retry:
        log_warn(f"Worker auto-update ({source}): retrying pending update apply for version {latest_version}.")

    updates_dir = APP_ROOT / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    package_path = updates_dir / f"bill-worker-{latest_version}.zip"

    # Pull identity from state so we can report progress to bill-core
    _report_machine_uuid = str(state.get("machine_uuid") or "")
    _report_machine_name = str(state.get("machine_name") or "")

    def _status(s: str, error: str | None = None) -> None:
        if _report_machine_uuid and runtime_state is not None:
            _report_update_status(
                machine_name=_report_machine_name,
                machine_uuid=_report_machine_uuid,
                runtime_state=runtime_state,
                update_status=s,
                update_target_version=latest_version,
                update_error=error,
            )

    try:
        log_info(
            f"Worker auto-update ({source}): current={WORKER_VERSION} latest={latest_version} package_url={package_url}"
        )
        log_info(f"Downloading worker update {latest_version} from {package_url} ({source})")
        _status("downloading")
        _download_update_package(package_url, package_path)
        log_info(f"Downloaded update package to {package_path}")

        if package_sha256:
            actual_sha = _compute_sha256(package_path).lower()
            if actual_sha != package_sha256:
                raise ValueError(
                    f"Update package SHA256 mismatch: expected={package_sha256} actual={actual_sha}"
                )

        log_info(f"Worker auto-update ({source}): launching updater helper process")
        _status("installing")

        exe_path = Path(sys.executable).resolve()
        _launch_windows_updater(package_path=package_path, app_root=APP_ROOT, executable_path=exe_path, updater_script_url=updater_script_url)
        # Secondary safety net in case updater relaunch is blocked by timing/desktop-session issues.
        _launch_restart_watchdog(app_root=APP_ROOT, delay_seconds=20)
        log_warn("Worker auto-update: updater launched, worker will exit for file replacement.")
        state["pending_update_version"] = latest_version
        state["update_pending"] = True
        pending = dict(state.get("pending_update") or {})
        pending.update(
            {
                "update_available": True,
                "latest_version": latest_version,
                "package_url": package_url,
                "package_sha256": package_sha256,
                "source": source,
                "launched_at": datetime.utcnow().isoformat(),
                "retry_count": int(pending.get("retry_count") or 0),
            }
        )
        state["pending_update"] = pending
        state.pop("update_last_error", None)
        save_state(state)
        log_warn(f"Applying worker update to version {latest_version}. Worker will restart.")
        return True
    except Exception as error:
        _status("failed", error=str(error))
        error_str = str(error)
        # If the package URL returned a 404, the cached URL is stale (release replaced).
        # Clear pending_update so the next cycle does a fresh check instead of retrying the bad URL.
        is_404 = "404" in error_str
        if is_404:
            state.pop("pending_update", None)
            state.pop("pending_update_version", None)
            state.pop("update_pending", None)
            state["update_last_error"] = error_str
            save_state(state)
            log_error(f"Worker auto-update failed ({source}) - stale release URL (404), will re-check: {error_str}")
        else:
            pending = dict(state.get("pending_update") or {})
            pending["retry_count"] = int(pending.get("retry_count") or 0) + 1
            pending["last_error"] = error_str
            pending["last_error_at"] = datetime.utcnow().isoformat()
            state["pending_update"] = pending
            state["update_pending"] = True
            state["update_last_error"] = error_str
            save_state(state)
            log_error(f"Worker auto-update failed ({source}): {error_str}")
        return False


def maybe_apply_update_from_registration(
    registration_payload: dict[str, Any] | None,
    state: dict[str, Any],
    runtime_state: RuntimeState | None = None,
) -> bool:
    if not isinstance(registration_payload, dict):
        return False

    update_payload = registration_payload.get("update")
    if not isinstance(update_payload, dict):
        return False

    return _apply_update_payload(update_payload, state, source="register-push", runtime_state=runtime_state)


def maybe_apply_update_on_connect(
    machine_uuid: str,
    state: dict[str, Any],
    runtime_state: RuntimeState | None = None,
) -> bool:
    payload: dict[str, Any] = {}
    check_url = f"{API_BASE}/worker/update/check"
    try:
        _log_http_start(
            "update-check",
            check_url,
            timeout=20,
            params={"machine_uuid": machine_uuid, "current_version": WORKER_VERSION},
        )
        response = _core_request(
            "GET",
            check_url,
            params={"machine_uuid": machine_uuid, "current_version": WORKER_VERSION},
            timeout=20,
        )
        response.raise_for_status()
        try:
            payload = response.json() if response.content else {}
        except ValueError:
            _log_non_json_response("update-check", check_url, response)
            return False
        if isinstance(payload, dict):
            log_info(
                "Auto-update check result: "
                f"update_available={bool(payload.get('update_available'))} "
                f"latest_version={payload.get('latest_version')}"
            )
    except Exception as error:
        _log_http_failure("update-check", check_url, error)
        return False

    return _apply_update_payload(
        payload if isinstance(payload, dict) else {},
        state,
        source="endpoint-fallback",
        runtime_state=runtime_state,
    )


def maybe_apply_queued_update(machine_uuid: str, state: dict[str, Any], runtime_state: RuntimeState) -> bool:
    if runtime_state.is_busy():
        return False

    pending_payload = _get_pending_update_payload(state)
    pending_version = str(state.get("pending_update_version") or "").strip()
    if not pending_payload and pending_version:
        log_info(
            f"Pending update version {pending_version} exists without package metadata; refreshing from core before retry."
        )
        return maybe_apply_update_on_connect(machine_uuid, state, runtime_state=runtime_state)

    if not pending_payload:
        return False

    log_warn(
        f"Applying queued update on idle worker: target_version={pending_payload.get('latest_version')}"
    )
    return _apply_update_payload(
        pending_payload,
        state,
        source="queued-retry",
        runtime_state=runtime_state,
        allow_pending_retry=True,
    )


def register_worker(machine_name: str, machine_uuid: str, runtime_state: RuntimeState) -> dict[str, Any] | None:
    snap = runtime_state.snapshot()
    register_url = f"{API_BASE}/worker/register"
    payload = {
        "machine_name": machine_name,
        "machine_uuid": machine_uuid,
        "worker_version": WORKER_VERSION,
        "execution_mode": snap["execution_mode"],
        "current_task_id": snap["current_task_id"],
        "current_step": snap["current_step"],
    }
    try:
        _log_http_start("register", register_url, timeout=10)
        log_info(
            "HTTP register payload: "
            f"machine_uuid={payload['machine_uuid']} machine_name={payload['machine_name']} "
            f"worker_version={payload['worker_version']} execution_mode={payload['execution_mode']}"
        )
        response = _core_request(
            "POST",
            register_url,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        log_info(
            "HTTP register response: "
            f"url={register_url} status={response.status_code} body={_request_body_snippet(response)!r}"
        )
        try:
            data = response.json()
        except ValueError:
            runtime_state.set_connected(False)
            _log_non_json_response("register", register_url, response)
            return None
        token = str(data.get("token") or "").strip()
        runtime_state.set_connected(True)
        connection_confirmed = bool(data.get("connection_confirmed", True))
        update_payload = data.get("update") if isinstance(data, dict) else None
        force_update = bool(update_payload.get("force_update")) if isinstance(update_payload, dict) else False
        log_info(
            f"Registration succeeded. url={register_url} status={response.status_code} "
            f"token={token} connection_confirmed={connection_confirmed} force_update={force_update}"
        )
        return data if isinstance(data, dict) else None
    except Exception as error:
        runtime_state.set_connected(False)
        _log_http_failure("register", register_url, error)
        return None


def _report_update_status(
    machine_name: str,
    machine_uuid: str,
    runtime_state: RuntimeState,
    update_status: str,
    update_target_version: str,
    update_error: str | None = None,
) -> None:
    """Send a heartbeat to bill-core carrying an update progress status."""
    snap = runtime_state.snapshot()
    heartbeat_url = f"{API_BASE}/worker/heartbeat"
    try:
        _core_request(
            "POST",
            heartbeat_url,
            json={
                "machine_name": machine_name,
                "machine_uuid": machine_uuid,
                "status": snap["status"],
                "worker_version": WORKER_VERSION,
                "execution_mode": snap["execution_mode"],
                "current_task_id": snap["current_task_id"],
                "current_step": snap["current_step"],
                "update_status": update_status,
                "update_target_version": update_target_version,
                "update_error": update_error,
            },
            timeout=10,
        )
    except Exception:
        pass  # Non-critical; don't interrupt the update flow


def send_heartbeat(machine_name: str, machine_uuid: str, runtime_state: RuntimeState) -> None:
    snap = runtime_state.snapshot()
    heartbeat_url = f"{API_BASE}/worker/heartbeat"
    try:
        _log_http_start("heartbeat", heartbeat_url, timeout=10)
        response = _core_request(
            "POST",
            heartbeat_url,
            json={
                "machine_name": machine_name,
                "machine_uuid": machine_uuid,
                "status": snap["status"],
                "worker_version": WORKER_VERSION,
                "execution_mode": snap["execution_mode"],
                "current_task_id": snap["current_task_id"],
                "current_step": snap["current_step"],
                "browser_profile_policy": snap["browser_profile_policy"],
                "bill_profile_ready": snap["bill_profile_ready"],
                "bookmarks_ready": snap["bookmarks_ready"],
                "debug_port_ready": snap["debug_port_ready"],
            },
            timeout=10,
        )
        response.raise_for_status()
        runtime_state.set_connected(True)
        log_info(
            "Heartbeat sent. "
            f"url={heartbeat_url} status={response.status_code} "
            f"status={snap['status']} mode={snap['execution_mode']} "
            f"task={snap['current_task_id']} step={snap['current_step']}"
        )
    except Exception as error:
        runtime_state.set_connected(False)
        _log_http_failure("heartbeat", heartbeat_url, error)


def _post_teaching_session_status(
    api_base: str,
    session_id: str,
    task_id: str,
    status: str,
    message: str = "",
) -> bool:
    """Tell Core that a teaching browser has opened (status=active) or failed."""
    if not session_id:
        return False
    url = f"{api_base.rstrip('/')}/api/teaching/session/{session_id}/status"
    body = {"status": status, "task_id": task_id or None, "message": message}
    last_error = ""
    for attempt in range(1, 4):
        try:
            resp = _core_request("POST", url, json=body, timeout=10)
            if resp.ok:
                log_info(
                    f"[worker] TEACHING_SESSION_{status.upper()} session_id={session_id} task_id={task_id}"
                )
                return True
            last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            log_warn(
                "[worker] teaching session status update failed "
                f"attempt={attempt}/3 session_id={session_id} error={last_error}"
            )
        except Exception as exc:
            last_error = repr(exc)
            log_warn(
                "[worker] teaching session status callback error "
                f"attempt={attempt}/3 session_id={session_id} error={last_error}"
            )

        if attempt < 3:
            time.sleep(float(attempt))

    log_error(
        "[worker] TEACHING_SESSION_STATUS_CALLBACK_FAILED "
        f"session_id={session_id} task_id={task_id} status={status} error={last_error}"
    )
    return False


def _run_teach_session(payload: dict[str, Any], update_step: Any) -> dict[str, Any]:
    """Run the teach session browser on this worker machine so Playwright opens
    locally (on the employee's computer, not the bill-core server).

    Imports teach_session directly rather than spawning a subprocess so that
    this works correctly when running as a PyInstaller-compiled exe (where
    sys.executable is the exe itself, not a Python interpreter).
    """
    import importlib.util
    import sys as _sys

    draft_id = str(payload.get("draft_id") or "")
    teach_session_id = str(payload.get("session_id") or "")
    requested_api_base = str(payload.get("api_base") or "").strip()
    api_base = requested_api_base.rstrip("/")
    if not api_base.startswith(("http://", "https://")):
        api_base = str(API_BASE).strip().rstrip("/")
    parsed_api_base = urlparse(api_base)
    if (parsed_api_base.path or "").rstrip("/").lower() == "/api/proxy":
        log_warn(
            f"[worker] teach_session received proxy api_base={requested_api_base!r}; "
            f"falling back to worker API base {API_BASE}"
        )
        api_base = str(API_BASE).strip().rstrip("/")
    start_url = str(payload.get("start_url") or "").strip() or None

    if not draft_id:
        raise WorkflowExecutionError("teach_session missing draft_id", {"status": "error", "error": "missing draft_id"})

    profile_policy = str(payload.get("browser_profile_policy") or BROWSER_PROFILE_POLICY or "bill_profile").strip().lower()
    if profile_policy not in {"bill_profile", "isolated_temp_profile", "attach_existing_debug"}:
        profile_policy = "bill_profile"
    chrome_user_data_dir = _resolve_bill_chrome_profile_dir(payload.get("bill_chrome_profile_dir") or BILL_CHROME_PROFILE_DIR)
    chrome_profile_directory = str(payload.get("chrome_profile_directory") or CHROME_PROFILE_DIRECTORY or "Default").strip() or "Default"
    remote_debugging_port = max(1, int(payload.get("remote_debugging_port") or REMOTE_DEBUGGING_PORT or 9222))
    launch_command = (
        f"chrome --remote-debugging-port={remote_debugging_port} "
        f"--user-data-dir={chrome_user_data_dir} "
        f"--profile-directory={chrome_profile_directory} --start-maximized"
    )

    update_step("provisioning Bill Teaching bookmarks")
    bookmark_result = provision_bill_teaching_bookmarks(chrome_user_data_dir, BILL_BOOKMARKS)
    update_step("launching teach session browser")
    log_info(f"[worker] teach_session task payload api_base={api_base}")
    log_info(f"[worker] teach_session task payload start_url={start_url or ''}")
    log_info(f"[worker] teach_session browser_profile_policy={profile_policy}")
    log_info(f"[worker] teach_session final Chrome launch command: {launch_command}")
    log_info(f"[worker] teach_session bookmark file path: {bookmark_result.get('bookmarks_path')}")
    log_info(f"[worker] launching teach session: draft_id={draft_id} api_base={api_base}")

    # Try importing teach_session — it's compiled into the exe as a module.
    # Fall back to loading from the filesystem (dev / non-frozen mode).
    try:
        import teach_session as _ts
    except ImportError:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "teach_session.py")
        if not os.path.isfile(script_path):
            raise WorkflowExecutionError(
                "teach_session module not found",
                {"status": "error", "error": "teach_session module not found"},
            )
        spec = importlib.util.spec_from_file_location("teach_session", script_path)
        _ts = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(_ts)  # type: ignore[union-attr]

    try:
        # Post the active callback immediately when Chrome opens (not after the
        # entire session ends), so the frontend poll doesn't time out.
        active_callback_sent: list[bool] = [False]

        def _on_browser_ready() -> None:
            active_callback_sent[0] = True
            _post_teaching_session_status(
                api_base=api_base,
                session_id=teach_session_id,
                task_id=str(payload.get("task_id") or ""),
                status="active",
                message="Teaching browser opened successfully. Walk me through the workflow.",
            )

        session_result = _ts.run_session(
            draft_id,
            api_base,
            start_url,
            session_id=teach_session_id,
            chrome_user_data_dir=str(chrome_user_data_dir),
            profile_directory=chrome_profile_directory,
            remote_debugging_port=remote_debugging_port,
            worker_shared_secret=WORKER_SHARED_SECRET,
            on_browser_ready=_on_browser_ready,
        )
        browser_launch_succeeded = bool((session_result or {}).get("browser_launch_succeeded"))
        log_info(f"[worker] teach_session browser launch succeeded={browser_launch_succeeded}")

        if teach_session_id and bool((session_result or {}).get("tab_mismatch_detected")):
            mismatch_message = str(
                (session_result or {}).get("tab_mismatch_message")
                or "Bill is not attached to the page you are using. Use the browser window Bill opened."
            )
            _post_teaching_session_status(
                api_base=api_base,
                session_id=teach_session_id,
                task_id=str(payload.get("task_id") or ""),
                status="active",
                message=mismatch_message,
            )

        # ── If browser never became ready, post failure now ───────────────────
        if teach_session_id and not active_callback_sent[0]:
            _post_teaching_session_status(
                api_base=api_base,
                session_id=teach_session_id,
                task_id=str(payload.get("task_id") or ""),
                status="failed" if not browser_launch_succeeded else "active",
                message=(
                    "Teaching browser opened successfully. Walk me through the workflow."
                    if browser_launch_succeeded
                    else "Teaching browser launch was not confirmed."
                ),
            )

        if not browser_launch_succeeded:
            raise WorkflowExecutionError(
                "Teach session browser launch was not confirmed",
                {
                    "status": "error",
                    "draft_id": draft_id,
                    "api_base": api_base,
                    "start_url": start_url or "",
                    "final_chrome_launch_command": launch_command,
                    "browser_launch_succeeded": False,
                },
            )

        return {
            "status": "completed",
            "draft_id": draft_id,
            "api_base": api_base,
            "start_url": start_url or "",
            "final_chrome_launch_command": launch_command,
            "browser_launch_succeeded": True,
            "browser_profile_policy": profile_policy,
            "bill_profile_ready": True,
            "bookmarks_ready": bool(bookmark_result.get("status") in {"ok", "skipped_profile_running"}),
            "debug_port_ready": True,
            "bookmarks": bookmark_result,
            **(session_result or {}),
        }
    except WorkflowExecutionError:
        if teach_session_id:
            _post_teaching_session_status(
                api_base=api_base,
                session_id=teach_session_id,
                task_id=str(payload.get("task_id") or ""),
                status="failed",
                message="Teaching session failed before browser could open.",
            )
        raise
    except Exception as exc:
        if teach_session_id:
            _post_teaching_session_status(
                api_base=api_base,
                session_id=teach_session_id,
                task_id=str(payload.get("task_id") or ""),
                status="failed",
                message=f"Teaching session error: {exc}",
            )
        raise WorkflowExecutionError(
            f"teach_session failed: {exc}",
            {
                "status": "error",
                "draft_id": draft_id,
                "api_base": api_base,
                "start_url": start_url or "",
                "final_chrome_launch_command": launch_command,
                "browser_launch_succeeded": False,
                "error": str(exc),
            },
        ) from exc


def poll_next_task(machine_uuid: str, state: dict[str, Any], runtime_state: RuntimeState) -> None:
    poll_url = f"{API_BASE}/worker/tasks/next"
    try:
        params = {"machine_uuid": machine_uuid}
        _log_http_start("task-poll", poll_url, timeout=10, params=params)
        response = _core_request("GET", poll_url, params=params, timeout=10)
        response.raise_for_status()
        try:
            task = response.json()
        except ValueError:
            _log_non_json_response("task-poll", poll_url, response)
            runtime_state.set_connected(False)
            return
        runtime_state.set_connected(True)
        log_info(f"Task poll response: url={poll_url} status={response.status_code} has_task={bool(task)}")
        if task:
            print(f"[worker] task received: {task.get('id')}")
            process_task(machine_uuid, task, state, runtime_state)
    except Exception as error:
        runtime_state.set_connected(False)
        _log_http_failure("task-poll", poll_url, error)


def poll_recovery_actions(machine_uuid: str, state: dict[str, Any], runtime_state: RuntimeState) -> None:
    """
    Poll for recovery actions on paused tasks assigned to this machine.
    Fetch pending recovery actions, execute them, and report results back to core.
    """
    import asyncio
    from recovery_handlers import execute_recovery_action

    def _checkpoint_updates_for_action(action_name: str, success: bool, recovery_context: dict[str, Any]) -> dict[str, Any]:
        if not success:
            return {}
        if action_name == "close_extra_tabs":
            return {"open_tabs_count": 1}
        if action_name == "dismiss_product_review_modal":
            return {"blocking_modal_detected": False, "modal_type": ""}
        if action_name == "skip_last_client":
            last_client = str(recovery_context.get("last_client_attempted") or "").strip()
            updates: dict[str, Any] = {}
            if last_client:
                updates["clients_skipped_addition"] = [last_client]
            return updates
        return {}

    try:
        list_url = f"{API_BASE}/api/tasks/paused-for-human-recovery"
        params = {"machine_uuid": machine_uuid, "include_auto": "true"}
        _log_http_start("recovery-poll", list_url, timeout=10, params=params)
        response = _core_request("GET", list_url, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json() if response.content else {}
        paused_tasks = payload.get("tasks") if isinstance(payload, dict) else []
        if not isinstance(paused_tasks, list):
            return

        for paused_task in paused_tasks:
            task_id = str(paused_task.get("id") or "").strip()
            if not task_id:
                continue

            recovery_context = paused_task.get("recovery_context") or {}
            recovery_actions = paused_task.get("recovery_actions") or []
            pending_actions = [a for a in recovery_actions if str(a.get("status") or "") == "pending"]

            for action_record in pending_actions:
                action_id = str(action_record.get("action_id") or "").strip()
                action_name = str(action_record.get("action") or "").strip()
                if not action_id or not action_name:
                    continue

                success = False
                result_message = ""
                error_details = ""
                checkpoint_updates: dict[str, Any] = {}

                if action_name in {"playbook_auto_sequence", "suggested_action_sequence"}:
                    sequence = action_record.get("action_sequence") or []
                    stop_on_first_failure = bool(action_record.get("stop_on_first_failure", True))
                    sequence_results: list[dict[str, Any]] = []
                    success = True

                    for sequence_action in sequence:
                        one_success, one_message = asyncio.run(
                            execute_recovery_action(sequence_action, None, recovery_context)
                        )
                        sequence_results.append(
                            {
                                "action": sequence_action,
                                "success": bool(one_success),
                                "message": one_message,
                            }
                        )
                        if one_success:
                            checkpoint_updates.update(_checkpoint_updates_for_action(sequence_action, True, recovery_context))
                        elif stop_on_first_failure:
                            success = False
                            break

                    if stop_on_first_failure:
                        success = success and all(item.get("success") for item in sequence_results)
                    else:
                        success = any(item.get("success") for item in sequence_results)

                    result_message = json.dumps({"sequence_results": sequence_results})
                    if not success:
                        first_failure = next((item for item in sequence_results if not item.get("success")), None)
                        error_details = str((first_failure or {}).get("message") or "playbook action sequence failed")
                else:
                    one_success, one_message = asyncio.run(execute_recovery_action(action_name, None, recovery_context))
                    success = bool(one_success)
                    result_message = str(one_message or "")
                    if success:
                        checkpoint_updates = _checkpoint_updates_for_action(action_name, True, recovery_context)
                    else:
                        error_details = result_message or "recovery action failed"

                completed_url = f"{API_BASE}/api/tasks/{task_id}/recovery-action-completed"
                completed_payload = {
                    "action_id": action_id,
                    "success": success,
                    "machine_uuid": machine_uuid,
                    "result_message": result_message,
                    "error_details": error_details,
                    "checkpoint_updates": checkpoint_updates,
                    "resume_recommended": success,
                }

                _log_http_start("recovery-complete", completed_url, timeout=15)
                completed_response = _core_request("POST", completed_url, json=completed_payload, timeout=15)
                completed_response.raise_for_status()
                log_info(
                    f"Recovery action completed: task_id={task_id} action_id={action_id} "
                    f"action={action_name} success={success}"
                )
    except Exception as error:
        _log_http_failure("recovery-poll", f"{API_BASE}/api/tasks/paused-for-human-recovery", error)


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _coerce_int(value: Any, default: int, minimum: int = 0, maximum: int = 120) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _parse_wait_times(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("wait_times")
    if isinstance(raw, dict):
        retry_delays = raw.get("retry_delays_ms")
        if isinstance(retry_delays, list):
            retry_delays = [_coerce_int(item, 0, minimum=0, maximum=120000) for item in retry_delays]
        else:
            retry_delays = []
        return {
            "retry_delays_ms": retry_delays,
            "step_delay_ms": _coerce_int(raw.get("step_delay_ms"), 0, minimum=0, maximum=60000),
            "timeout_ms": _coerce_int(raw.get("timeout_ms"), 15000, minimum=1000, maximum=300000),
        }

    if isinstance(raw, list):
        return {
            "retry_delays_ms": [_coerce_int(item, 0, minimum=0, maximum=120000) for item in raw],
            "step_delay_ms": 0,
            "timeout_ms": 15000,
        }

    return {
        "retry_delays_ms": [],
        "step_delay_ms": 0,
        "timeout_ms": 15000,
    }


def _extract_execution_controls(payload: dict[str, Any]) -> dict[str, Any]:
    selector_strategy = str(payload.get("selector_strategy") or "balanced").strip().lower()
    if selector_strategy not in {"strict", "balanced", "fallback"}:
        selector_strategy = "balanced"

    workflow_variation = str(payload.get("workflow_variation") or "").strip()
    debug_outputs = payload.get("debug_outputs")
    if not isinstance(debug_outputs, dict):
        debug_outputs = {}

    return {
        "retry_attempts": _coerce_int(payload.get("retry_attempts"), 0, minimum=0, maximum=8),
        "wait_times": _parse_wait_times(payload),
        "selector_strategy": selector_strategy,
        "workflow_variation": workflow_variation,
        "debug_outputs": {
            "screenshots": bool(debug_outputs.get("screenshots", False)),
            "dom_snapshots": bool(debug_outputs.get("dom_snapshots", False)),
        },
    }


def _apply_workflow_variation(payload: dict[str, Any], workflow_variation: str) -> dict[str, Any]:
    if not workflow_variation:
        return payload

    variations = payload.get("workflow_variations")
    if not isinstance(variations, dict):
        return payload

    selected = variations.get(workflow_variation)
    if not isinstance(selected, dict):
        return payload

    merged = dict(payload)
    merged.update(selected)
    merged["workflow_variation_applied"] = workflow_variation
    return merged


def _retry_delay_for_attempt(wait_times: dict[str, Any], attempt_index: int) -> int:
    delays = wait_times.get("retry_delays_ms") or []
    if isinstance(delays, list) and attempt_index - 1 < len(delays):
        return _coerce_int(delays[attempt_index - 1], 0, minimum=0, maximum=120000)
    return 0


def _append_feedback(
    execution_feedback: list[dict[str, Any]],
    step_name: str,
    success: bool,
    reason: str,
    retries_attempted: int,
    started_at: str,
    finished_at: str,
    attempt: int,
) -> None:
    execution_feedback.append(
        {
            "step_name": step_name,
            "success": bool(success),
            "reason": str(reason),
            "retries_attempted": int(max(0, retries_attempted)),
            "started_at": started_at,
            "finished_at": finished_at,
            "attempt": int(max(1, attempt)),
        }
    )


def process_task(machine_uuid: str, task: dict, state: dict[str, Any], runtime_state: RuntimeState) -> None:
    task_id = task.get("id")
    payload = dict(task.get("payload") or {})
    task_type = payload.get("task_type")
    secrets = load_secrets()
    default_worker_mode = DEFAULT_WORKER_MODE
    execution_controls = _extract_execution_controls(payload)
    payload = _apply_workflow_variation(payload, str(execution_controls.get("workflow_variation") or ""))

    wait_times = execution_controls.get("wait_times") or {}
    step_delay_ms = _coerce_int(wait_times.get("step_delay_ms"), 0, minimum=0, maximum=60000)
    timeout_ms = _coerce_int(wait_times.get("timeout_ms"), 15000, minimum=1000, maximum=300000)
    selector_strategy = str(execution_controls.get("selector_strategy") or "balanced")
    debug_outputs = dict(execution_controls.get("debug_outputs") or {})

    payload.setdefault("selector_strategy", selector_strategy)
    payload.setdefault("debug_outputs", debug_outputs)
    if step_delay_ms > 0:
        payload.setdefault("step_delay_ms", step_delay_ms)
    if timeout_ms > 0:
        payload.setdefault("timeout_ms", timeout_ms)

    retry_attempts = _coerce_int(execution_controls.get("retry_attempts"), 0, minimum=0, maximum=8)
    max_attempts = max(1, retry_attempts + 1)
    execution_feedback: list[dict[str, Any]] = []
    browser_task_types = {
        "browser_workflow",
        "taught_workflow",
        "open_url_and_screenshot",
        "click_selector",
        "type_text",
        "wait_for_element",
        "smart_sherpa_sync",
        "teach_session",
    }

    if task_type == "browser_workflow":
        execution_mode = _normalize_mode(str(payload.get("mode") or "interactive_visible"), "interactive_visible")
    elif task_type in {"taught_workflow", "open_url_and_screenshot", "click_selector", "type_text", "wait_for_element", "smart_sherpa_sync"}:
        execution_mode = _normalize_mode(str(payload.get("mode") if payload.get("mode") else default_worker_mode), default_worker_mode)
    else:
        execution_mode = default_worker_mode

    if execution_mode == "interactive_visible":
        print("[worker] SAFETY: visible execution is active. Do not use this machine simultaneously.")

    runtime_state.set_busy(task_id=task_id, mode=execution_mode, step="starting task")

    if task_type in browser_task_types:
        policy = str(payload.get("browser_profile_policy") or BROWSER_PROFILE_POLICY or "bill_profile").strip().lower()
        if policy not in {"bill_profile", "isolated_temp_profile", "attach_existing_debug"}:
            policy = "bill_profile"
        payload.setdefault("browser_profile_policy", policy)
        payload.setdefault("bill_chrome_profile_dir", str(BILL_CHROME_PROFILE_DIR))
        payload.setdefault("bill_bookmarks", [dict(item) for item in BILL_BOOKMARKS])
        payload.setdefault("chrome_profile_directory", CHROME_PROFILE_DIRECTORY)
        payload.setdefault("remote_debugging_port", REMOTE_DEBUGGING_PORT)
        payload.setdefault("prefer_system_chrome", PREFER_SYSTEM_CHROME)
        runtime_state.set_browser_profile_status(
            policy=policy,
            bill_profile_ready=(policy != "isolated_temp_profile"),
            bookmarks_ready=False,
            debug_port_ready=False,
        )

    machine_name = socket.gethostname()
    task_heartbeat_stop = threading.Event()
    task_heartbeat_thread: threading.Thread | None = None

    def start_task_heartbeat_loop() -> None:
        """Keep heartbeats flowing during long-running task handlers.

        teach_session can stay inside Playwright for several minutes; without
        periodic heartbeats, core marks the worker offline after stale last_seen.
        """

        heartbeat_interval = max(2.0, min(float(HEARTBEAT_INTERVAL_SECONDS), 10.0))

        def _loop() -> None:
            while not task_heartbeat_stop.wait(heartbeat_interval):
                try:
                    send_heartbeat(machine_name, machine_uuid, runtime_state)
                except Exception as heartbeat_error:
                    print(f"[worker] task heartbeat loop warning: {heartbeat_error}")

        nonlocal task_heartbeat_thread
        task_heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        task_heartbeat_thread.start()

    send_heartbeat(machine_name, machine_uuid, runtime_state)
    start_task_heartbeat_loop()

    current_attempt = 1

    def update_step(step_text: str) -> None:
        runtime_state.set_step(step_text)
        print(f"[worker] current step: {step_text}")
        now_iso = _now_iso()
        _append_feedback(
            execution_feedback,
            step_name=step_text,
            success=True,
            reason="in_progress",
            retries_attempted=max(0, current_attempt - 1),
            started_at=now_iso,
            finished_at=now_iso,
            attempt=current_attempt,
        )
        send_heartbeat(machine_name, machine_uuid, runtime_state)

    try:
        result_json: dict[str, Any] | None = None
        workflow_error: WorkflowExecutionError | None = None
        generic_error: Exception | None = None
        fallback_url = state.get("last_url")

        for attempt in range(1, max_attempts + 1):
            current_attempt = attempt
            attempt_start = _now_iso()
            runtime_state.set_step(f"attempt {attempt}/{max_attempts}")
            send_heartbeat(machine_name, machine_uuid, runtime_state)

            try:
                if task_type == "open_url_and_screenshot":
                    result_json = run_open_url_and_screenshot(
                        payload,
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "browser_workflow":
                    result_json = run_browser_workflow(
                        payload,
                        secret_resolver=lambda name: resolve_secret_value(name, secrets),
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "taught_workflow":
                    result_json = run_taught_workflow(
                        payload,
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "click_selector":
                    result_json = run_click_selector(
                        payload,
                        fallback_url=fallback_url,
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "type_text":
                    result_json = run_type_text(
                        payload,
                        fallback_url=fallback_url,
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "wait_for_element":
                    result_json = run_wait_for_element(
                        payload,
                        fallback_url=fallback_url,
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "smart_sherpa_sync":
                    result_json = run_smart_sherpa_sync(
                        payload,
                        progress_callback=update_step,
                        default_mode=execution_mode,
                    )
                elif task_type == "teach_session":
                    result_json = _run_teach_session(payload, update_step)
                else:
                    print(f"[worker] unsupported or test task type '{task_type}', marking complete")
                    result_json = {"task_type": task_type or "unknown", "status": "completed_noop"}

                if isinstance(result_json, dict) and task_type in browser_task_types:
                    runtime_state.set_browser_profile_status(
                        policy=str(result_json.get("browser_profile_policy") or payload.get("browser_profile_policy") or "bill_profile"),
                        bill_profile_ready=bool(result_json.get("bill_profile_ready", payload.get("browser_profile_policy") != "isolated_temp_profile")),
                        bookmarks_ready=bool(result_json.get("bookmarks_ready", False)),
                        debug_port_ready=bool(result_json.get("debug_port_ready", False)),
                    )
                    send_heartbeat(machine_name, machine_uuid, runtime_state)

                _append_feedback(
                    execution_feedback,
                    step_name=f"task:{task_type or 'unknown'}",
                    success=True,
                    reason="attempt_completed",
                    retries_attempted=max(0, attempt - 1),
                    started_at=attempt_start,
                    finished_at=_now_iso(),
                    attempt=attempt,
                )
                workflow_error = None
                generic_error = None
                break
            except WorkflowExecutionError as error:
                workflow_error = error
                _append_feedback(
                    execution_feedback,
                    step_name=f"task:{task_type or 'unknown'}",
                    success=False,
                    reason=str(error),
                    retries_attempted=max(0, attempt - 1),
                    started_at=attempt_start,
                    finished_at=_now_iso(),
                    attempt=attempt,
                )
            except Exception as error:
                generic_error = error
                _append_feedback(
                    execution_feedback,
                    step_name=f"task:{task_type or 'unknown'}",
                    success=False,
                    reason=str(error),
                    retries_attempted=max(0, attempt - 1),
                    started_at=attempt_start,
                    finished_at=_now_iso(),
                    attempt=attempt,
                )

            if attempt < max_attempts:
                delay_ms = _retry_delay_for_attempt(wait_times, attempt)
                runtime_state.set_step(f"retry wait {delay_ms}ms before attempt {attempt + 1}")
                send_heartbeat(machine_name, machine_uuid, runtime_state)
                if delay_ms > 0:
                    time.sleep(delay_ms / 1000.0)

        if result_json is None and workflow_error is not None:
            raise workflow_error
        if result_json is None and generic_error is not None:
            raise generic_error
        if result_json is None:
            raise RuntimeError("Task produced no result")

        result_json = dict(result_json)
        result_json["adaptive_execution"] = {
            "retry_attempts": retry_attempts,
            "wait_times": wait_times,
            "selector_strategy": selector_strategy,
            "workflow_variation": payload.get("workflow_variation_applied") or execution_controls.get("workflow_variation") or "",
            "debug_outputs": debug_outputs,
        }
        result_json["execution_feedback"] = execution_feedback

        result_url = (result_json or {}).get("url")
        if result_url:
            state["last_url"] = result_url
            save_state(state)

        complete_task(machine_uuid, task_id, result_json)
        print(f"[worker] task marked complete: {task_id}")
        runtime_state.set_idle(mode=execution_mode)
        send_heartbeat(machine_name, machine_uuid, runtime_state)
    except WorkflowExecutionError as error:
        print(f"[worker] workflow failed for task {task_id}: {error}")
        error_result = dict(error.result_json or {})
        error_result.setdefault("adaptive_execution", {
            "retry_attempts": retry_attempts,
            "wait_times": wait_times,
            "selector_strategy": selector_strategy,
            "workflow_variation": payload.get("workflow_variation_applied") or execution_controls.get("workflow_variation") or "",
            "debug_outputs": debug_outputs,
        })
        error_result["execution_feedback"] = execution_feedback
        fail_task(machine_uuid, task_id, str(error), error_result)
        runtime_state.set_error(str(error), mode=execution_mode)
        runtime_state.set_idle(mode=execution_mode)
        send_heartbeat(machine_name, machine_uuid, runtime_state)
    except Exception as error:
        print(f"[worker] error processing task {task_id}: {error}")
        error_result_json = getattr(error, "result_json", None)
        if not isinstance(error_result_json, dict):
            error_result_json = {}
        fail_task(
            machine_uuid,
            task_id,
            str(error),
            {
                "task_type": task_type,
                **error_result_json,
                "adaptive_execution": {
                    "retry_attempts": retry_attempts,
                    "wait_times": wait_times,
                    "selector_strategy": selector_strategy,
                    "workflow_variation": payload.get("workflow_variation_applied") or execution_controls.get("workflow_variation") or "",
                    "debug_outputs": debug_outputs,
                },
                "execution_feedback": execution_feedback,
            },
        )
        runtime_state.set_error(str(error), mode=execution_mode)
        runtime_state.set_idle(mode=execution_mode)
        send_heartbeat(machine_name, machine_uuid, runtime_state)
    finally:
        task_heartbeat_stop.set()
        if task_heartbeat_thread and task_heartbeat_thread.is_alive():
            task_heartbeat_thread.join(timeout=2)


def start_local_status_panel(machine_name: str, machine_uuid_getter: callable, runtime_state: RuntimeState) -> None:
    print("[worker-ui] Launching embedded Tk status panel.")

    try:
        import tkinter as tk
    except Exception as error:
        print(f"[worker-ui] tkinter unavailable; local status panel disabled: {error}")
        return

    def run_panel() -> None:
        selenium_state: dict[str, Any] = {"driver": None}

        def is_debug_chrome_ready(port: int) -> bool:
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
                return resp.ok and bool(resp.text)
            except Exception:
                return False

        def launch_debug_chrome_with_selenium() -> None:
            def run_attach() -> None:
                try:
                    profile_cfg = resolve_bill_chrome_profile(
                        {
                            "browser_profile_policy": "bill_profile",
                            "bill_chrome_profile_dir": str(BILL_CHROME_PROFILE_DIR),
                            "chrome_profile_directory": CHROME_PROFILE_DIRECTORY,
                            "remote_debugging_port": REMOTE_DEBUGGING_PORT,
                            "bill_bookmarks": [dict(item) for item in BILL_BOOKMARKS],
                            "prefer_system_chrome": PREFER_SYSTEM_CHROME,
                        },
                        executor_name="local_status_panel_selenium",
                    )
                    debug_port = int(profile_cfg.get("remote_debugging_port") or REMOTE_DEBUGGING_PORT)

                    bookmark_result = provision_bill_bookmarks(
                        profile_cfg["bill_chrome_profile_dir"],
                        profile_cfg.get("bill_bookmarks") or [],
                    )
                    launch_result = launch_bill_chrome_with_debug(profile_cfg, logger=log_info)

                    runtime_state.set_browser_profile_status(
                        policy=str(profile_cfg.get("browser_profile_policy") or "bill_profile"),
                        bill_profile_ready=True,
                        bookmarks_ready=bool(bookmark_result.get("bookmarks_ready", False)),
                        debug_port_ready=bool(launch_result.get("debug_port_ready", False)),
                    )

                    if not is_debug_chrome_ready(debug_port):
                        runtime_state.set_error(f"Chrome debug endpoint unavailable on 127.0.0.1:{debug_port}")
                        return

                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options

                    options = Options()
                    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
                    options.add_experimental_option("detach", True)

                    driver = webdriver.Chrome(options=options)
                    selenium_state["driver"] = driver
                    runtime_state.set_step("Selenium attached to debug Chrome")
                except Exception as error:
                    runtime_state.set_error(f"Selenium attach failed: {error}")

            threading.Thread(target=run_attach, daemon=True).start()

        root = tk.Tk()
        root.title("Bill Worker Status")
        root.geometry("720x280")
        root.resizable(False, False)

        labels: dict[str, tk.Label] = {}

        def add_row(title: str, row: int) -> None:
            tk.Label(root, text=f"{title}:", anchor="w", width=18, font=("Segoe UI", 10, "bold")).grid(
                row=row,
                column=0,
                sticky="w",
                padx=10,
                pady=4,
            )
            value = tk.Label(root, text="-", anchor="w", width=46, font=("Segoe UI", 10))
            value.grid(row=row, column=1, sticky="w", padx=8, pady=4)
            labels[title] = value

        add_row("Connection", 0)
        add_row("Machine Name", 1)
        add_row("Machine UUID", 2)
        add_row("Status", 3)
        add_row("Mode", 4)
        add_row("Current Task", 5)
        add_row("Current Step", 6)

        note = tk.Label(
            root,
            text="Visible mode warning: avoid using this desktop while Bill is automating.",
            anchor="w",
            fg="red",
            font=("Segoe UI", 9),
        )
        note.grid(row=7, column=0, columnspan=2, sticky="w", padx=10, pady=8)

        attach_btn = tk.Button(
            root,
            text="Open Chrome Debug + Attach Selenium",
            command=launch_debug_chrome_with_selenium,
            bg="#1565c0",
            fg="white",
            padx=10,
            pady=4,
        )
        attach_btn.grid(row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(2, 8))

        def refresh() -> None:
            snap = runtime_state.snapshot()

            labels["Connection"].config(text="Connected" if snap["connected"] else "Disconnected")
            labels["Machine Name"].config(text=machine_name)
            labels["Machine UUID"].config(text=machine_uuid_getter() or "-")
            labels["Status"].config(text=snap["status"])
            labels["Mode"].config(text=snap["execution_mode"])
            labels["Current Task"].config(text=snap["current_task_id"] or "-")
            labels["Current Step"].config(text=snap["current_step"] or "-")

            root.after(500, refresh)

        refresh()
        root.mainloop()

    thread = threading.Thread(target=run_panel, daemon=False)
    thread.start()


def complete_task(machine_uuid: str, task_id: str | None, result_json: dict[str, Any] | None = None) -> None:
    if not task_id:
        return

    try:
        _core_request(
            "POST",
            f"{API_BASE}/worker/tasks/{task_id}/complete",
            json={"machine_uuid": machine_uuid, "result_json": result_json},
            timeout=10,
        ).raise_for_status()
        print(f"Task marked complete: {task_id}")
    except requests.RequestException as error:
        print(f"Complete task failed: {error}")


def fail_task(machine_uuid: str, task_id: str | None, error_message: str, result_json: dict[str, Any] | None = None) -> None:
    if not task_id:
        return

    try:
        web_resilience = (result_json or {}).get("web_resilience") if isinstance(result_json, dict) else None
        if isinstance(web_resilience, dict):
            detected_modals = web_resilience.get("detected_modals") or []
            detected_overlays = web_resilience.get("detected_overlays") or []
            failed_action = str(web_resilience.get("failed_action") or "")
            print(
                "[worker] WEB_RESILIENCE_SNAPSHOT "
                f"task_id={task_id} "
                f"failed_action={failed_action} "
                f"detected_modals={len(detected_modals)} "
                f"detected_overlays={len(detected_overlays)}"
            )
        _core_request(
            "POST",
            f"{API_BASE}/worker/tasks/{task_id}/fail",
            json={
                "machine_uuid": machine_uuid,
                "error": error_message,
                "result_json": result_json,
            },
            timeout=10,
        ).raise_for_status()
        print(f"[worker] task marked failed: {task_id}")
    except requests.RequestException as error:
        print(f"[worker] fail task update failed: {error}")


def provision_bill_teaching_bookmarks(profile_dir: Path, bookmarks: list[dict[str, Any]]) -> dict[str, Any]:
    result = provision_bill_bookmarks(profile_dir, bookmarks)
    log_info(f"[bookmarks] profile_path={profile_dir}")
    log_info(f"[bookmarks] bookmark_file={result.get('bookmarks_path')}")
    log_info(f"[bookmarks] added={result.get('added')}")
    log_info(f"[bookmarks] updated={result.get('updated')}")
    log_info(f"[bookmarks] skipped={result.get('skipped')}")
    return result


def launch_bill_teaching_chrome(profile_dir: Path, start_url: str | None = None, remote_debugging_port: int = 9222) -> list[str]:
    profile = resolve_bill_chrome_profile(
        {
            "browser_profile_policy": "bill_profile",
            "bill_chrome_profile_dir": str(profile_dir),
            "chrome_profile_directory": CHROME_PROFILE_DIRECTORY,
            "remote_debugging_port": remote_debugging_port,
            "bill_bookmarks": BILL_BOOKMARKS,
        },
        executor_name="setup_chrome_profile",
    )
    launch_result = launch_bill_chrome_with_debug(profile, start_url=start_url, logger=log_info)
    log_info(f"[bookmarks] Chrome launched with profile_path={profile_dir}")
    return list(launch_result.get("launch_command") or [])


def run_setup_chrome_profile() -> int:
    profile_dir = BILL_CHROME_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)

    result = provision_bill_teaching_bookmarks(profile_dir, BILL_BOOKMARKS)
    launch_bill_teaching_chrome(profile_dir, remote_debugging_port=REMOTE_DEBUGGING_PORT)

    print("Log into required systems once, then close Chrome.")
    print(f"Profile path: {profile_dir}")
    print(f"Bookmark file path: {result.get('bookmarks_path')}")
    return 0


def _validate_playwright_chromium() -> dict[str, Any]:
    """Check that Playwright and Chromium are available; auto-install Chromium if missing.

    Logs Python path, Playwright version, Chromium exe path, and whether the
    browser binary was found.  If Chromium is missing, attempts a subprocess
    install and logs the outcome.  Never raises — a missing browser is
    surfaced as a clear error in the log so the operator can act.
    """
    log_info(f"[playwright-check] Python executable : {sys.executable}")

    # Check Playwright package
    try:
        version = importlib_metadata.version("playwright")
        log_info(f"[playwright-check] Playwright version : {version}")
    except ImportError:
        log_warn("[playwright-check] playwright package is NOT installed — teach sessions will fail")
        system_chrome = _detect_system_chrome_path()
        ui_allowed = WORKER_UI_ENABLED and system_chrome is not None
        browser_mode = "system_chrome" if system_chrome is not None else "none"
        log_info("[playwright-check] bundled_chromium_found=false")
        log_info(f"[playwright-check] system_chrome_found={str(system_chrome is not None).lower()}")
        log_info(f"[playwright-check] browser_mode selected: {browser_mode}")
        log_info(f"[playwright-check] worker_ui_launch_allowed={str(ui_allowed).lower()}")
        return {
            "bundled_chromium_found": False,
            "system_chrome_found": system_chrome is not None,
            "browser_mode": browser_mode,
            "worker_ui_launch_allowed": ui_allowed,
        }
    except Exception as exc:
        log_warn(f"[playwright-check] Could not resolve Playwright version: {exc}")

    browsers_path = _configure_playwright_browsers_path()
    log_info(f"[playwright-check] PLAYWRIGHT_BROWSERS_PATH : {browsers_path}")

    chromium_exe = _resolve_playwright_chromium_executable()
    bundled_chromium_found = bool(chromium_exe and Path(chromium_exe).exists())
    system_chrome = _detect_system_chrome_path()
    system_chrome_found = system_chrome is not None

    if bundled_chromium_found:
        log_info(f"[playwright-check] Chromium exe : {chromium_exe} (OK)")
    else:
        log_warn(f"[playwright-check] Chromium NOT found at: {chromium_exe or '(unknown)'}")

    if PREFER_SYSTEM_CHROME and system_chrome_found:
        browser_mode = "system_chrome"
    elif bundled_chromium_found:
        browser_mode = "bundled_chromium"
    elif system_chrome_found:
        browser_mode = "system_chrome"
    else:
        browser_mode = "none"

    worker_ui_launch_allowed = WORKER_UI_ENABLED
    log_info(f"[playwright-check] bundled_chromium_found={str(bundled_chromium_found).lower()}")
    log_info(f"[playwright-check] system_chrome_found={str(system_chrome_found).lower()}")
    log_info(f"[playwright-check] browser_mode selected: {browser_mode}")
    log_info(f"[playwright-check] worker_ui_launch_allowed={str(worker_ui_launch_allowed).lower()}")

    # Never block worker UI/startup on browser installation.
    if (not bundled_chromium_found) and (not system_chrome_found):
        log_info("[playwright-check] scheduling background playwright install chromium")
        threading.Thread(target=lambda: _attempt_playwright_install_chromium(timeout_seconds=120), daemon=True).start()
    elif not bundled_chromium_found:
        log_info("[playwright-check] skipping automatic playwright install: system Chrome fallback available")

    return {
        "bundled_chromium_found": bundled_chromium_found,
        "system_chrome_found": system_chrome_found,
        "browser_mode": browser_mode,
        "worker_ui_launch_allowed": worker_ui_launch_allowed,
    }


def main() -> None:
    setup_chrome_profile = any(arg.strip().lower() == "--setup-chrome-profile" for arg in sys.argv[1:])
    manual_update_trigger = any(arg.strip().lower() == "--trigger-update-now" for arg in sys.argv[1:])

    startup_log_path = initialize_logging()
    log_info("Starting Bill Worker...")
    log_info(f"App root: {APP_ROOT}")
    log_info(f"Startup log: {startup_log_path}")
    _log_startup_environment()

    for required_dir in [LOGS_DIR, SCREENSHOTS_DIR, DOWNLOADS_DIR]:
        required_dir.mkdir(parents=True, exist_ok=True)

    runtime_settings = apply_runtime_config()
    log_info(f"Worker version: {WORKER_VERSION}")
    _log_startup_environment(runtime_settings)

    if setup_chrome_profile:
        log_info("Running setup command: --setup-chrome-profile")
        run_setup_chrome_profile()
        return

    browser_status = _validate_playwright_chromium()
    log_info(
        "Startup browser summary: "
        f"bundled_chromium_found={browser_status.get('bundled_chromium_found')} "
        f"system_chrome_found={browser_status.get('system_chrome_found')} "
        f"browser_mode={browser_status.get('browser_mode')} "
        f"worker_ui_launch_allowed={browser_status.get('worker_ui_launch_allowed')}"
    )

    machine_name = str(MACHINE_DISPLAY_NAME_OVERRIDE or socket.gethostname()).strip()
    log_info(f"Worker name: {machine_name}")
    log_info(f"Core URL: {runtime_settings['core_url']}")
    log_info(f"Visible mode: {runtime_settings['visible_mode']}")
    log_info(f"Auto update enabled: {runtime_settings['auto_update_enabled']}")
    log_info(f"Default mode: {runtime_settings['default_execution_mode']}")
    log_info(f"Log level: {runtime_settings['log_level']}")
    log_info(f"Prefer system Chrome: {runtime_settings['prefer_system_chrome']}")
    log_info(f"Screenshots path: {runtime_settings['screenshots_dir']}")
    log_info(f"Downloads path: {runtime_settings['downloads_dir']}")
    log_info(f"Heartbeat interval: {runtime_settings['heartbeat_interval_seconds']}s")
    log_info(f"Polling interval: {runtime_settings['polling_interval_seconds']}s")
    log_info(f"Update check interval: {runtime_settings['update_check_interval_seconds']}s")
    log_info(f"Connection mode: API_BASE={API_BASE} default_mode={DEFAULT_WORKER_MODE}")
    log_info(f"Worker API endpoints: register={API_BASE}/worker/register heartbeat={API_BASE}/worker/heartbeat poll={API_BASE}/worker/tasks/next")
    log_info(f"Bill Chrome profile path: {runtime_settings['bill_chrome_profile_dir']}")
    log_info(f"Bill bookmark entries configured: {runtime_settings['bill_bookmarks_count']}")
    log_info(f"Chrome profile directory: {runtime_settings['chrome_profile_directory']}")
    log_info(f"Remote debugging port: {runtime_settings['remote_debugging_port']}")
    log_info(f"Browser profile policy default: {runtime_settings['browser_profile_policy']}")

    state = load_state()

    pending_update_version = str(state.get("pending_update_version") or "").strip()
    if pending_update_version:
        if not _is_newer_version(pending_update_version, WORKER_VERSION):
            log_info(
                f"Startup detected completed update to {WORKER_VERSION}; clearing pending_update_version={pending_update_version}."
            )
            state.pop("pending_update_version", None)
            state.pop("pending_update", None)
            state.pop("update_pending", None)
            state.pop("update_last_error", None)
            save_state(state)
        else:
            log_warn(
                f"Startup detected pending update target={pending_update_version} while running version={WORKER_VERSION}."
            )

    if str(state.get("pending_update_version") or "").strip() and str(state.get("update_last_error") or "").strip():
        log_warn(f"Pending update last error: {state.get('update_last_error')}")

    runtime_state = RuntimeState(
        status="idle",
        execution_mode=DEFAULT_WORKER_MODE,
    )

    machine_uuid = state.get("machine_uuid")
    if not machine_uuid:
        machine_uuid = str(uuid.uuid4())
        state["machine_uuid"] = machine_uuid

    # Keep machine_name in state so _apply_update_payload can read it for status reporting
    state["machine_name"] = machine_name
    save_state(state)

    if WORKER_UI_ENABLED:
        start_local_status_panel(machine_name, machine_uuid_getter=lambda: machine_uuid, runtime_state=runtime_state)

    if manual_update_trigger:
        log_warn("Manual update trigger requested via --trigger-update-now")

    token = state.get("token")
    registration_payload: dict[str, Any] | None = None
    registration_ready = False
    last_register_attempt = 0.0
    register_retry_seconds = max(10.0, POLLING_INTERVAL_SECONDS)
    log_info("Startup sequence step 1/3: register")
    registration_payload = register_worker(machine_name, machine_uuid, runtime_state)
    token = str((registration_payload or {}).get("token") or "").strip() or None
    last_register_attempt = time.time()
    if token:
        state["token"] = token
        save_state(state)
        registration_ready = True
    else:
        registration_ready = False
        log_warn("Initial registration failed. Worker will retry registration before heartbeat/task polling.")

    if registration_ready and token:
        if maybe_apply_update_from_registration(registration_payload, state, runtime_state=runtime_state):
            log_warn("Worker exiting cleanly to allow updater to replace files.")
            return

        connection_confirmed = bool((registration_payload or {}).get("connection_confirmed", True))
        pushed_update = (registration_payload or {}).get("update")
        forced_update_pending = bool(pushed_update.get("force_update")) if isinstance(pushed_update, dict) else False

        if not connection_confirmed and forced_update_pending:
            log_error("Core requires forced update before worker can attach. Update did not complete; exiting.")
            return

        should_exit_for_update = maybe_apply_update_on_connect(machine_uuid, state, runtime_state=runtime_state)
        if should_exit_for_update:
            log_warn("Worker exiting cleanly to allow updater to replace files.")
            return

    if manual_update_trigger:
        if maybe_apply_update_on_connect(machine_uuid, state, runtime_state=runtime_state):
            log_warn("Manual update trigger launched updater. Worker exiting cleanly.")
            return
        log_info("Manual update trigger completed: no update applied.")

    last_heartbeat = 0.0
    last_task_poll = 0.0
    last_update_check = 0.0

    try:
        while True:
            now = time.time()
            core_backoff = CORE_CONNECTIVITY.current_backoff()
            next_allowed_in = CORE_CONNECTIVITY.seconds_until_next_attempt()

            LAST_RUNTIME_SNAPSHOT.update(runtime_state.snapshot())

            if next_allowed_in > 0:
                runtime_state.set_connected(False)
                # Keep loop responsive while honoring outage backoff.
                time.sleep(min(1.0, next_allowed_in))
                continue

            effective_register_retry = max(register_retry_seconds, core_backoff)
            if (not registration_ready) and (now - last_register_attempt) >= effective_register_retry:
                log_warn("Retrying registration with Bill Core...")
                registration_payload = register_worker(machine_name, machine_uuid, runtime_state)
                token = str((registration_payload or {}).get("token") or "").strip() or None
                last_register_attempt = now
                if token:
                    state["token"] = token
                    save_state(state)
                    registration_ready = True
                    if maybe_apply_update_from_registration(registration_payload, state, runtime_state=runtime_state):
                        log_warn("Worker exiting cleanly to allow updater to replace files.")
                        return

                    connection_confirmed = bool((registration_payload or {}).get("connection_confirmed", True))
                    pushed_update = (registration_payload or {}).get("update")
                    forced_update_pending = bool(pushed_update.get("force_update")) if isinstance(pushed_update, dict) else False

                    if not connection_confirmed and forced_update_pending:
                        log_error("Core requires forced update before worker can attach. Update did not complete; exiting.")
                        return

                    should_exit_for_update = maybe_apply_update_on_connect(machine_uuid, state, runtime_state=runtime_state)
                    if should_exit_for_update:
                        log_warn("Worker exiting cleanly to allow updater to replace files.")
                        return

            if not registration_ready:
                runtime_state.set_connected(False)
                time.sleep(1)
                continue

            effective_heartbeat_interval = max(HEARTBEAT_INTERVAL_SECONDS, core_backoff)
            if now - last_heartbeat >= effective_heartbeat_interval:
                log_info("Startup sequence step 2/3: heartbeat") if last_heartbeat == 0.0 else None
                send_heartbeat(machine_name, machine_uuid, runtime_state)
                last_heartbeat = now

            effective_poll_interval = max(POLLING_INTERVAL_SECONDS, core_backoff)
            if now - last_task_poll >= effective_poll_interval:
                log_info("Startup sequence step 3/3: task poll") if last_task_poll == 0.0 else None
                poll_next_task(machine_uuid, state, runtime_state)
                poll_recovery_actions(machine_uuid, state, runtime_state)
                last_task_poll = now

            effective_update_check_interval = max(UPDATE_CHECK_INTERVAL_SECONDS, core_backoff)
            if AUTO_UPDATE_ENABLED and (now - last_update_check) >= effective_update_check_interval:
                if runtime_state.snapshot().get("status") == "idle":
                    if maybe_apply_queued_update(machine_uuid, state, runtime_state):
                        log_warn("Worker exiting cleanly to allow updater to replace files.")
                        return
                    if maybe_apply_update_on_connect(machine_uuid, state, runtime_state=runtime_state):
                        log_warn("Worker exiting cleanly to allow updater to replace files.")
                        return
                else:
                    if str(state.get("pending_update_version") or "").strip():
                        log_info("Worker is busy; pending update remains queued until idle.")
                last_update_check = now

            time.sleep(1)
    except Exception as loop_error:
        snap = runtime_state.snapshot()
        log_error(
            "WORKER_MAIN_LOOP_CRASH "
            f"error={loop_error!r} status={snap.get('status')} task={snap.get('current_task_id')} step={snap.get('current_step')}"
        )
        active_task_id = str(snap.get("current_task_id") or "").strip()
        if active_task_id:
            fail_task(
                str(machine_uuid),
                active_task_id,
                f"Worker fatal loop crash: {loop_error}",
                {
                    "status": "worker_crash",
                    "last_step": snap.get("current_step"),
                    "last_mode": snap.get("execution_mode"),
                },
            )
        raise


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_warn("Worker stopped by user interrupt.")
        sys.exit(130)
    except Exception as error:
        traceback_text = traceback.format_exc()
        try:
            if LAST_RUNTIME_SNAPSHOT:
                log_error(
                    "WORKER_FATAL_STATE "
                    f"machine_uuid={LAST_MACHINE_UUID} "
                    f"status={LAST_RUNTIME_SNAPSHOT.get('status')} "
                    f"task={LAST_RUNTIME_SNAPSHOT.get('current_task_id')} "
                    f"step={LAST_RUNTIME_SNAPSHOT.get('current_step')} "
                    f"connected={LAST_RUNTIME_SNAPSHOT.get('connected')}"
                )
            if "Tcl_AsyncDelete" in str(error) or "tk" in str(error).lower():
                log_error("Detected Tcl/Tk shutdown exception; worker core loop state captured above.")
            log_error(f"Startup failure: {error!r}")
            print(traceback_text, file=sys.stderr, end="")
        except Exception:
            print(f"Startup failure: {error!r}", file=sys.stderr)
            print(traceback_text, file=sys.stderr, end="")

        fatal_log_path = _write_fatal_startup_log(error, traceback_text)
        if fatal_log_path is not None:
            print(f"[worker] Fatal startup log written to: {fatal_log_path}", file=sys.stderr)

        startup_error_log_path = _write_startup_error_log(error, traceback_text)
        if startup_error_log_path is not None:
            print(f"[worker] Startup error log written to: {startup_error_log_path}", file=sys.stderr)

        _show_startup_error_message_box()

        if _is_windows_interactive_session():
            try:
                input("Fatal startup error. Press Enter to exit...")
            except EOFError:
                pass

        sys.exit(1)
