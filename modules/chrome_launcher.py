"""
Shared Chrome debug-mode launcher used by observation mode and the worker UI.

Design goals
------------
- Single source of truth for Chrome launch parameters.
- Check for an existing live debug session before launching.
- Poll the /json/version endpoint instead of blind sleep.
- Use one consistent dedicated debug-profile path (data/chrome_debug_profile).
- Never kill unrelated Chrome instances by default.
- Report success only when the debug endpoint is confirmed reachable.
- Optional force_fresh flag (default False) for intentional restarts.
"""

from __future__ import annotations

import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

_DEFAULT_DEBUG_PORT = 9222
_DEFAULT_POLL_TIMEOUT_S = 12.0     # how long to wait for port to come up
_DEFAULT_POLL_INTERVAL_S = 0.4


def _repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _default_profile_dir() -> Path:
    """All debug Chrome instances use this single profile directory."""
    return Path(_repo_root()) / "data" / "chrome_debug_profile"


def _detect_chrome_path() -> str | None:
    candidates = [
        os.getenv("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.join(os.getenv("LOCALAPPDATA") or "", r"Google\Chrome\Application\chrome.exe"),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def is_debug_port_ready(port: int = _DEFAULT_DEBUG_PORT) -> bool:
    """Return True if Chrome's remote debugging endpoint is responding."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=1.5
        ) as resp:
            return bool(resp.read())
    except Exception:
        return False


def _poll_until_ready(
    port: int,
    timeout_s: float,
    interval_s: float,
    log: Callable[[str], None],
) -> bool:
    deadline = time.time() + timeout_s
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        if is_debug_port_ready(port):
            log(f"Chrome debug port {port} is ready (poll attempt {attempt}).")
            return True
        log(f"Waiting for Chrome debug port {port}… (attempt {attempt})")
        time.sleep(interval_s)
    return False


def _try_kill_debug_profile_chrome(profile_dir: Path, log: Callable[[str], None]) -> None:
    """
    Best-effort: kill only Chrome processes that were launched with our
    dedicated debug profile directory.  Does NOT kill the user's main
    Chrome session.
    """
    profile_str = str(profile_dir.resolve()).lower()
    try:
        result = subprocess.run(
            ["wmic", "process", "where", "name='chrome.exe'", "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            if profile_str in line.lower():
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    pid_str = parts[-1].strip()
                    if pid_str.isdigit():
                        try:
                            subprocess.run(["taskkill", "/F", "/PID", pid_str], capture_output=True)
                            log(f"Killed stale debug Chrome (pid={pid_str}).")
                        except Exception:
                            pass
    except Exception as err:
        log(f"Debug Chrome kill attempt skipped: {err}")


def launch_debug_chrome(
    log: Callable[[str], None] | None = None,
    port: int | None = None,
    profile_dir: Path | None = None,
    initial_url: str = "about:blank",
    force_fresh: bool = False,
    poll_timeout_s: float = _DEFAULT_POLL_TIMEOUT_S,
    poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
) -> bool:
    """
    Ensure a Chrome debug session is running and reachable.

    Parameters
    ----------
    log             : callable that accepts a str message (defaults to print)
    port            : remote debugging port (default 9222 or CHROME_DEBUG_PORT env)
    profile_dir     : user-data-dir for the debug profile (default data/chrome_debug_profile)
    initial_url     : URL opened on launch (default about:blank)
    force_fresh     : if True, kill the existing debug-profile Chrome first
    poll_timeout_s  : how long to wait for the port to come up
    poll_interval_s : polling interval

    Returns
    -------
    True  — debug endpoint is confirmed reachable (safe to attach Selenium)
    False — could not bring up a reachable debug session
    """
    if log is None:
        log = print

    resolved_port = int(port or os.getenv("CHROME_DEBUG_PORT", str(_DEFAULT_DEBUG_PORT)) or _DEFAULT_DEBUG_PORT)
    resolved_profile = profile_dir or _default_profile_dir()

    log(f"[ChromeLauncher] debug port={resolved_port}  profile={resolved_profile}")

    # ------------------------------------------------------------------
    # Step 1: Check whether a live debug session already exists.
    # ------------------------------------------------------------------
    if not force_fresh and is_debug_port_ready(resolved_port):
        log(f"[ChromeLauncher] Existing debug Chrome found on port {resolved_port} — reusing.")
        return True

    # ------------------------------------------------------------------
    # Step 2: If force_fresh, kill our debug-profile Chrome first.
    # ------------------------------------------------------------------
    if force_fresh:
        log("[ChromeLauncher] force_fresh=True — stopping existing debug-profile Chrome.")
        _try_kill_debug_profile_chrome(resolved_profile, log)
        time.sleep(0.8)

    # ------------------------------------------------------------------
    # Step 3: Locate Chrome executable.
    # ------------------------------------------------------------------
    chrome_path = _detect_chrome_path()
    if not chrome_path:
        log("[ChromeLauncher] FAIL: Chrome executable not found. Set CHROME_PATH env var.")
        return False
    log(f"[ChromeLauncher] Chrome executable: {chrome_path}")

    # ------------------------------------------------------------------
    # Step 4: Ensure profile directory exists.
    # ------------------------------------------------------------------
    try:
        resolved_profile.mkdir(parents=True, exist_ok=True)
    except Exception as mkdir_err:
        log(f"[ChromeLauncher] WARNING: could not create profile dir: {mkdir_err}")

    # ------------------------------------------------------------------
    # Step 5: Launch Chrome with debug flags.
    # ------------------------------------------------------------------
    launch_cmd = [
        chrome_path,
        f"--remote-debugging-port={resolved_port}",
        f"--user-data-dir={str(resolved_profile.resolve())}",
        "--no-first-run",
        "--no-default-browser-check",
        initial_url,
    ]
    log(f"[ChromeLauncher] Launching: {' '.join(launch_cmd)}")
    try:
        subprocess.Popen(launch_cmd, cwd=_repo_root())
    except Exception as launch_err:
        log(f"[ChromeLauncher] FAIL: Popen raised: {launch_err}")
        return False

    # ------------------------------------------------------------------
    # Step 6: Poll readiness.
    # ------------------------------------------------------------------
    log(f"[ChromeLauncher] Polling port {resolved_port} (timeout={poll_timeout_s}s)…")
    ready = _poll_until_ready(resolved_port, poll_timeout_s, poll_interval_s, log)

    if ready:
        log(f"[ChromeLauncher] SUCCESS — Chrome debug session ready on port {resolved_port}.")
        return True

    # ------------------------------------------------------------------
    # Step 7: Diagnose why it failed.
    # ------------------------------------------------------------------
    log(
        f"[ChromeLauncher] FAIL — port {resolved_port} did not become reachable within "
        f"{poll_timeout_s}s. Possible causes:\n"
        f"  • Another non-debug Chrome instance swallowed the launch (single-instance handoff).\n"
        f"  • The profile directory is locked by another Chrome process.\n"
        f"  • Chrome crashed on startup.\n"
        f"  Tip: close all Chrome windows and retry, or use force_fresh=True to kill the "
        f"  debug-profile Chrome first."
    )
    return False
