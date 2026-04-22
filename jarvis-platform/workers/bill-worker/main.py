import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
import hashlib
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
from worker.executors.type_text import run as run_type_text
from worker.executors.wait_for_element import run as run_wait_for_element

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
WORKER_VERSION = "0.3.30"
HEARTBEAT_INTERVAL_SECONDS = 10.0
POLLING_INTERVAL_SECONDS = 5.0
UPDATE_CHECK_INTERVAL_SECONDS = 120.0
AUTO_UPDATE_ENABLED = True
MACHINE_DISPLAY_NAME_OVERRIDE: str | None = None
DEFAULT_WORKER_MODE = "interactive_visible"
WORKER_UI_ENABLED = True
LOG_LEVEL = "INFO"

DEFAULT_CONFIG = {
    "core_url": DEFAULT_CORE_URL,
    "worker_name": socket.gethostname(),
    "visible_mode": True,
    "auto_update_enabled": True,
    "poll_interval_seconds": 5,
    "log_level": "INFO",
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


@dataclass
class RuntimeState:
    connected: bool = False
    status: str = "idle"
    execution_mode: str = "headless_background"
    current_task_id: str | None = None
    current_step: str | None = None
    last_error: str | None = None
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

    return merged


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

    config = load_worker_config()

    API_BASE = str(_get_setting(config, "core_url", ["BILL_CORE_URL", "JARVIS_CORE_URL"], DEFAULT_CORE_URL)).rstrip("/")
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

    WORKER_UI_ENABLED = True

    screenshots_dir = _resolve_dir(str(SCREENSHOTS_DIR), SCREENSHOTS_DIR, APP_ROOT)
    downloads_dir = _resolve_dir(str(DOWNLOADS_DIR), DOWNLOADS_DIR, APP_ROOT)

    screenshots_dir.mkdir(parents=True, exist_ok=True)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

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
        with requests.get(package_url, stream=True, timeout=60) as response:
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
            resp = requests.get(updater_script_url, timeout=15)
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
        response = requests.get(
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
        response = requests.post(
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
        requests.post(
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
        response = requests.post(
            heartbeat_url,
            json={
                "machine_name": machine_name,
                "machine_uuid": machine_uuid,
                "status": snap["status"],
                "worker_version": WORKER_VERSION,
                "execution_mode": snap["execution_mode"],
                "current_task_id": snap["current_task_id"],
                "current_step": snap["current_step"],
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

    launch_command = (
        "playwright.chromium.launch(headless=False, "
        "args=['--start-maximized', '--disable-infobars'])"
    )

    update_step("launching teach session browser")
    log_info(f"[worker] teach_session task payload api_base={api_base}")
    log_info(f"[worker] teach_session task payload start_url={start_url or ''}")
    log_info(f"[worker] teach_session final Chrome launch command: {launch_command}")
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
        session_result = _ts.run_session(draft_id, api_base, start_url)
        browser_launch_succeeded = bool((session_result or {}).get("browser_launch_succeeded"))
        log_info(f"[worker] teach_session browser launch succeeded={browser_launch_succeeded}")
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
            **(session_result or {}),
        }
    except WorkflowExecutionError:
        raise
    except Exception as exc:
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
        response = requests.get(poll_url, params=params, timeout=10)
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

    if task_type == "browser_workflow":
        execution_mode = _normalize_mode(str(payload.get("mode") or "interactive_visible"), "interactive_visible")
    elif task_type in {"open_url_and_screenshot", "click_selector", "type_text", "wait_for_element", "smart_sherpa_sync"}:
        execution_mode = _normalize_mode(str(payload.get("mode") if payload.get("mode") else default_worker_mode), default_worker_mode)
    else:
        execution_mode = default_worker_mode

    if execution_mode == "interactive_visible":
        print("[worker] SAFETY: visible execution is active. Do not use this machine simultaneously.")

    runtime_state.set_busy(task_id=task_id, mode=execution_mode, step="starting task")

    machine_name = socket.gethostname()
    send_heartbeat(machine_name, machine_uuid, runtime_state)

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
        fail_task(
            machine_uuid,
            task_id,
            str(error),
            {
                "task_type": task_type,
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


def start_local_status_panel(machine_name: str, machine_uuid_getter: callable, runtime_state: RuntimeState) -> None:
    try:
        import tkinter as tk
    except Exception as error:
        print(f"[worker-ui] tkinter unavailable; local status panel disabled: {error}")
        return

    def run_panel() -> None:
        selenium_state: dict[str, Any] = {"driver": None}

        def detect_chrome_path() -> Path:
            candidates = [
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            ]
            local_appdata = str(os.getenv("LOCALAPPDATA") or "").strip()
            if local_appdata:
                candidates.append(Path(local_appdata) / "Google" / "Chrome" / "Application" / "chrome.exe")

            for candidate in candidates:
                if candidate.exists():
                    return candidate
            raise FileNotFoundError("Google Chrome executable not found")

        def is_debug_chrome_ready(port: int) -> bool:
            try:
                resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
                return resp.ok and bool(resp.text)
            except Exception:
                return False

        def launch_debug_chrome_with_selenium() -> None:
            def run_attach() -> None:
                debug_port = 9222
                try:
                    if not is_debug_chrome_ready(debug_port):
                        chrome_path = detect_chrome_path()
                        profile_dir = APP_ROOT / "chrome-debug-profile"
                        profile_dir.mkdir(parents=True, exist_ok=True)
                        subprocess.Popen(
                            [
                                str(chrome_path),
                                f"--remote-debugging-port={debug_port}",
                                f"--user-data-dir={str(profile_dir)}",
                                "--no-first-run",
                                "--no-default-browser-check",
                            ],
                            cwd=str(APP_ROOT),
                        )

                        for _ in range(20):
                            if is_debug_chrome_ready(debug_port):
                                break
                            time.sleep(0.3)

                    if not is_debug_chrome_ready(debug_port):
                        runtime_state.set_error("Chrome debug endpoint unavailable on 127.0.0.1:9222")
                        return

                    from selenium import webdriver
                    from selenium.webdriver.chrome.options import Options

                    options = Options()
                    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{debug_port}")
                    options.add_experimental_option("detach", True)

                    driver = webdriver.Chrome(options=options)
                    driver.get("https://www.google.com")
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

    thread = threading.Thread(target=run_panel, daemon=True)
    thread.start()


def complete_task(machine_uuid: str, task_id: str | None, result_json: dict[str, Any] | None = None) -> None:
    if not task_id:
        return

    try:
        requests.post(
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
        requests.post(
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


def main() -> None:
    startup_log_path = initialize_logging()
    log_info("Starting Bill Worker...")
    log_info(f"App root: {APP_ROOT}")
    log_info(f"Startup log: {startup_log_path}")

    for required_dir in [LOGS_DIR, SCREENSHOTS_DIR, DOWNLOADS_DIR]:
        required_dir.mkdir(parents=True, exist_ok=True)

    runtime_settings = apply_runtime_config()
    log_info(f"Worker version: {WORKER_VERSION}")

    machine_name = str(MACHINE_DISPLAY_NAME_OVERRIDE or socket.gethostname()).strip()
    log_info(f"Worker name: {machine_name}")
    log_info(f"Core URL: {runtime_settings['core_url']}")
    log_info(f"Visible mode: {runtime_settings['visible_mode']}")
    log_info(f"Auto update enabled: {runtime_settings['auto_update_enabled']}")
    log_info(f"Default mode: {runtime_settings['default_execution_mode']}")
    log_info(f"Log level: {runtime_settings['log_level']}")
    log_info(f"Screenshots path: {runtime_settings['screenshots_dir']}")
    log_info(f"Downloads path: {runtime_settings['downloads_dir']}")
    log_info(f"Heartbeat interval: {runtime_settings['heartbeat_interval_seconds']}s")
    log_info(f"Polling interval: {runtime_settings['polling_interval_seconds']}s")
    log_info(f"Update check interval: {runtime_settings['update_check_interval_seconds']}s")
    log_info(f"Connection mode: API_BASE={API_BASE} default_mode={DEFAULT_WORKER_MODE}")
    log_info(f"Worker API endpoints: register={API_BASE}/worker/register heartbeat={API_BASE}/worker/heartbeat poll={API_BASE}/worker/tasks/next")

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

    manual_update_trigger = any(arg.strip().lower() == "--trigger-update-now" for arg in sys.argv[1:])
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

    while True:
        now = time.time()

        if (not registration_ready) and (now - last_register_attempt) >= register_retry_seconds:
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

        if now - last_heartbeat >= HEARTBEAT_INTERVAL_SECONDS:
            log_info("Startup sequence step 2/3: heartbeat") if last_heartbeat == 0.0 else None
            send_heartbeat(machine_name, machine_uuid, runtime_state)
            last_heartbeat = now

        if now - last_task_poll >= POLLING_INTERVAL_SECONDS:
            log_info("Startup sequence step 3/3: task poll") if last_task_poll == 0.0 else None
            poll_next_task(machine_uuid, state, runtime_state)
            last_task_poll = now

        if AUTO_UPDATE_ENABLED and (now - last_update_check) >= UPDATE_CHECK_INTERVAL_SECONDS:
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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_warn("Worker stopped by user interrupt.")
        sys.exit(130)
    except Exception as error:
        log_error(f"Startup failure: {error!r}")
        import traceback

        traceback.print_exc()
        raise
