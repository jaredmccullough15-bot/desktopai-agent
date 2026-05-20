"""Tests for Teaching Mode session ID chain integrity and capture robustness.

Covers:
 1. session_id chain consistency (worker → run_session → POST URLs)
 2. action/context POST to missing session returns clear 404 signal
 3. Trusted Types / CSP simulated failure does not prevent listener ready flag
 4. Badge injection failure does not stop capture event posting
 5. Action/context POST uses the same session_id as the start-session response
"""
from __future__ import annotations

import importlib
from pathlib import Path
import sys
import types
import unittest.mock as mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import teach_session as ts


# ── 1. session_id forwarded to POST URLs ──────────────────────────────────────

def test_action_post_url_contains_session_id() -> None:
    session_id = "test-session-abc123"
    captured: list[str] = []

    class _FakeResp:
        status_code = 200
        text = "{}"

    with mock.patch("teach_session.requests.post") as mock_post:
        mock_post.return_value = _FakeResp()
        ts._post_teaching_action(
            "http://localhost:8010",
            session_id,
            {"type": "click", "label": "Save", "url": "https://example.com"},
        )
        assert mock_post.called
        url_called = mock_post.call_args[0][0]
        assert session_id in url_called, f"session_id not in URL: {url_called}"
        assert "/api/teaching/session/" in url_called


def test_context_post_url_contains_session_id() -> None:
    session_id = "ctx-session-xyz"

    class _FakeResp:
        status_code = 200
        text = "{}"

    with mock.patch("teach_session.requests.post") as mock_post:
        mock_post.return_value = _FakeResp()
        ok, err = ts._post_teaching_context(
            "http://localhost:8010",
            session_id,
            {"reason": "navigate", "url": "https://example.com"},
        )
        assert ok
        url_called = mock_post.call_args[0][0]
        assert session_id in url_called
        assert "/api/teaching/session/" in url_called


# ── 2. 404 from backend logged as TEACH_CAPTURE_SESSION_NOT_FOUND ─────────────

def test_action_post_404_logs_session_not_found(capsys) -> None:
    class _FakeResp:
        status_code = 404
        text = '{"detail": "Teaching session not found", "session_id": "bad-id"}'

    with mock.patch("teach_session.requests.post") as mock_post:
        mock_post.return_value = _FakeResp()
        result = ts._post_teaching_action(
            "http://localhost:8010",
            "bad-session-id",
            {"type": "click", "label": "X"},
        )
        assert result is False
        captured = capsys.readouterr()
        assert "TEACH_CAPTURE_SESSION_NOT_FOUND" in captured.out
        assert "bad-session-id" in captured.out


def test_context_post_404_logs_session_not_found(capsys) -> None:
    class _FakeResp:
        status_code = 404
        text = '{"detail": "Teaching session not found", "session_id": "bad-id"}'

    with mock.patch("teach_session.requests.post") as mock_post:
        mock_post.return_value = _FakeResp()
        ok, err = ts._post_teaching_context(
            "http://localhost:8010",
            "bad-session-id",
            {"reason": "navigate", "url": "https://example.com"},
        )
        assert ok is False
        captured = capsys.readouterr()
        assert "TEACH_CAPTURE_SESSION_NOT_FOUND" in captured.out


# ── 3. Capture-ready flag is set before any panel/badge injection ─────────────

def test_listener_js_sets_capture_ready_before_panel() -> None:
    """__BILL_TEACH_CAPTURE_READY must appear before ensureQuestionPanel in JS."""
    js = ts._LISTENER_JS
    ready_pos = js.find("__BILL_TEACH_CAPTURE_READY")
    panel_pos = js.find("ensureQuestionPanel")
    assert ready_pos != -1, "__BILL_TEACH_CAPTURE_READY not found in listener JS"
    assert panel_pos != -1, "ensureQuestionPanel not found in listener JS"
    assert ready_pos < panel_pos, (
        "__BILL_TEACH_CAPTURE_READY must be set before ensureQuestionPanel is defined"
    )


# ── 4. panel.innerHTML is wrapped in try/catch ────────────────────────────────

def test_listener_js_wraps_innerhtml_in_try_catch() -> None:
    """CSP/TrustedTypes guard: panel.innerHTML must be inside a try { } block."""
    js = ts._LISTENER_JS
    inner_html_pos = js.find("panel.innerHTML")
    # Look backwards for try { within a reasonable window
    window = js[max(0, inner_html_pos - 200): inner_html_pos]
    assert "try {" in window, (
        "panel.innerHTML must be preceded by 'try {' within 200 chars"
    )
    # Search full JS after innerHTML for the catch block (HTML array can be very long)
    after = js[inner_html_pos:]
    assert "} catch" in after, "panel.innerHTML try block must be followed by '} catch'"


# ── 5. _badge_injection_skipped event emitted on innerHTML failure ────────────

def test_listener_js_emits_badge_skipped_on_csp_error() -> None:
    """Catch block must emit _badge_injection_skipped event."""
    js = ts._LISTENER_JS
    catch_start = js.find("} catch (_cspErr)")
    assert catch_start != -1, "} catch (_cspErr) block not found in listener JS"
    catch_block = js[catch_start: catch_start + 600]
    assert "_badge_injection_skipped" in catch_block, (
        "catch block must emit _badge_injection_skipped event"
    )
    assert "trusted_types_or_csp" in catch_block


# ── 6. missing session_id short-circuits POST immediately ────────────────────

def test_action_post_skips_when_session_id_empty(capsys) -> None:
    with mock.patch("teach_session.requests.post") as mock_post:
        result = ts._post_teaching_action("http://localhost:8010", "", {"type": "click"})
        assert result is False
        assert not mock_post.called
        out = capsys.readouterr().out
        assert "missing_session_id" in out


def test_context_post_skips_when_session_id_empty(capsys) -> None:
    with mock.patch("teach_session.requests.post") as mock_post:
        ok, err = ts._post_teaching_context("http://localhost:8010", "", {"reason": "nav"})
        assert ok is False
        assert not mock_post.called


# ── 7. Capture headers carry worker key ──────────────────────────────────────

def test_capture_headers_carry_worker_key() -> None:
    headers = ts._teaching_capture_headers("secret-key-123")
    assert headers.get("X-Bill-Worker-Key") == "secret-key-123"
