#!/usr/bin/env python3
"""
teach_session.py — Playwright browser instrumentation for Bill Teach Mode.

Launches a visible Chromium browser and observes:
  - URL navigations
  - Element clicks
  - Text input (captured on blur — final value only)
  - Select / dropdown changes

Each observed action is converted to a draft step and appended to the
active workflow learning draft via:
  POST /api/brain/workflow-learning/drafts/{draft_id}/steps/append

Usage:
    python teach_session.py \
        --draft-id <DRAFT_ID> \
        [--api-base http://127.0.0.1:8010] \
        [--start-url https://example.com]

Requirements (install into the same venv as bill-core):
    pip install playwright requests
    playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

try:
    import requests
except ImportError:
    print(
        "[teach] 'requests' not installed. Run: pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "[teach] 'playwright' not installed.\n"
        "  Run: pip install playwright && playwright install chromium",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_API_BASE = "http://127.0.0.1:8010"
APPEND_TIMEOUT = 8  # HTTP timeout seconds
EVENT_DEBOUNCE = 0.25  # Ignore exact-duplicate event types within this many seconds

# ── Browser-side listener (injected via add_init_script on every page load) ───
_LISTENER_JS = r"""
(function () {
    // Re-attach on every navigation — guard by storing the token on window so
    // we only ever attach ONE set of listeners even if the script re-runs.
    if (window.__billListenersAttached) { return; }
    window.__billListenersAttached = true;

    // Push events into a per-frame JS queue.  Python drains it via
    // frame.evaluate() on a 200 ms polling loop — no console.log used,
    // immune to console overrides, CSP, and cross-origin restrictions.
    if (!Array.isArray(window.__billEvents)) { window.__billEvents = []; }
    function emit(payload) {
        try { window.__billEvents.push(payload); }
        catch (err) { /* ignore */ }
    }

    function esc(s) { return s ? String(s).replace(/\\/g, '\\\\').replace(/"/g, '\\"') : ''; }

    function getInfo(el) {
        if (!el || el === document || el === document.body) return {};
        return {
            tag:         String(el.tagName || '').toLowerCase(),
            id:          el.id || '',
            name:        el.getAttribute('name')        || '',
            class_name:  typeof el.className === 'string' ? el.className : '',
            aria_label:  el.getAttribute('aria-label')  || '',
            data_testid: el.getAttribute('data-testid') || '',
            placeholder: el.getAttribute('placeholder') || '',
            text:        String(el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80),
            input_type:  String(el.getAttribute('type') || '').toLowerCase(),
            value:       el.value != null ? String(el.value) : '',
            href:        el.href  || '',
            role:        el.getAttribute('role') || '',
        };
    }

    function buildSelector(info) {
        if (info.id)
            return '#' + info.id.replace(/([^\w-])/g, '\\$1');
        if (info.data_testid)
            return '[data-testid="' + esc(info.data_testid) + '"]';
        if (info.aria_label)
            return '[aria-label="' + esc(info.aria_label) + '"]';
        if (info.name && ['input','select','textarea'].indexOf(info.tag) !== -1)
            return info.tag + '[name="' + esc(info.name) + '"]';
        if (info.text && ['button','a'].indexOf(info.tag) !== -1 && info.text.length < 50)
            return info.tag + ':has-text("' + esc(info.text.slice(0, 40)) + '")';
        if (info.class_name && info.tag) {
            var classes = info.class_name.trim().split(/\s+/)
                .filter(function(c) {
                    return c.length > 1 && c.length < 30 && !/[:()[\]{}]/.test(c);
                }).slice(0, 2);
            if (classes.length) return info.tag + '.' + classes.join('.');
        }
        return info.tag || 'div';
    }

    // Walk up the DOM to find the most meaningful interactive ancestor
    function findInteractive(el) {
        for (var i = 0; i < 8; i++) {
            if (!el || el === document.body) break;
            var t = String(el.tagName || '').toLowerCase();
            var role = el.getAttribute('role') || '';
            if (t === 'button' || t === 'a' || t === 'input' ||
                t === 'select' || t === 'textarea' ||
                role === 'button' || role === 'link' || role === 'tab' ||
                role === 'menuitem' || role === 'option' ||
                el.getAttribute('tabindex') === '0') {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    }

    /* ── Click ────────────────────────────────────────────── */
    document.addEventListener('click', function (e) {
        var raw = e.target;
        var el = findInteractive(raw) || raw;
        var info = getInfo(el);

        // Skip pure input fields (captured on blur instead)
        var t = info.tag;
        if (t === 'input' || t === 'textarea' || t === 'select') return;

        emit({
            event_type: 'click',
            selector:   buildSelector(info),
            element:    info,
            url:        window.location.href,
            ts:         Date.now(),
        });
    }, true);

    /* ── Text input (on blur = final value) ─────────────── */
    document.addEventListener('blur', function (e) {
        var el = e.target;
        if (!el) return;
        var t = String(el.tagName || '').toLowerCase();
        if (t !== 'input' && t !== 'textarea') return;
        if (!el.value) return;
        if (String(el.getAttribute('type') || '').toLowerCase() === 'password') return;
        var info = getInfo(el);
        emit({
            event_type: 'type_text',
            selector:   buildSelector(info),
            value:      el.value,
            element:    info,
            url:        window.location.href,
            ts:         Date.now(),
        });
    }, true);

    /* ── Select / dropdown ──────────────────────────────── */
    document.addEventListener('change', function (e) {
        var el = e.target;
        if (!el || String(el.tagName || '').toLowerCase() !== 'select') return;
        var info = getInfo(el);
        var selectedText = (el.options && el.selectedIndex >= 0)
            ? el.options[el.selectedIndex].text : '';
        emit({
            event_type:  'select_option',
            selector:    buildSelector(info),
            value:       el.value,
            option_text: selectedText,
            element:     info,
            url:         window.location.href,
            ts:          Date.now(),
        });
    }, true);

    /* ── Form submit ───────────────────────────────────── */
    document.addEventListener('submit', function (e) {
        var el = e.target;
        var info = getInfo(el);
        emit({
            event_type: 'submit',
            selector: buildSelector(info),
            element: info,
            url: window.location.href,
            ts: Date.now(),
        });
    }, true);

    function ensureQuestionPanel() {
        if (window.__billObservationPanel) { return window.__billObservationPanel; }
        if (!document.body) { return null; }

        var panel = document.createElement('div');
        panel.id = 'bill-observation-panel';
        panel.style.position = 'fixed';
        panel.style.top = '16px';
        panel.style.right = '16px';
        panel.style.width = '360px';
        panel.style.maxWidth = 'calc(100vw - 32px)';
        panel.style.background = 'rgba(17,24,39,0.96)';
        panel.style.color = '#f9fafb';
        panel.style.border = '1px solid rgba(148,163,184,0.35)';
        panel.style.borderRadius = '14px';
        panel.style.boxShadow = '0 16px 40px rgba(15,23,42,0.35)';
        panel.style.zIndex = '2147483647';
        panel.style.fontFamily = 'Segoe UI, Arial, sans-serif';
        panel.style.display = 'block';
        panel.style.overflow = 'hidden';
        panel.innerHTML = [
            '<div style="padding:12px 14px;border-bottom:1px solid rgba(148,163,184,0.2);display:flex;justify-content:space-between;align-items:center;gap:8px;">',
            '  <div>',
            '    <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#93c5fd;">Bill Observation</div>',
            '    <div id="bill-observation-trigger" style="font-size:13px;color:#cbd5e1;"></div>',
            '  </div>',
            '  <button id="bill-observation-pause" style="background:#0f172a;color:#f8fafc;border:1px solid rgba(148,163,184,0.35);border-radius:999px;padding:6px 10px;cursor:pointer;">Pause</button>',
            '</div>',
            '<div style="padding:14px;display:flex;flex-direction:column;gap:10px;">',
            '  <div id="bill-observation-question" style="font-size:15px;line-height:1.45;font-weight:600;"></div>',
            '  <div id="bill-observation-context" style="font-size:12px;color:#94a3b8;"></div>',
            '  <textarea id="bill-observation-answer" placeholder="Type what you are doing and why..." style="width:100%;min-height:92px;resize:vertical;border-radius:10px;border:1px solid rgba(148,163,184,0.35);background:#0f172a;color:#f8fafc;padding:10px 12px;font:inherit;"></textarea>',
            '  <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">',
            '    <button id="bill-observation-speak-question" style="background:#0ea5e9;color:#e0f2fe;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;">Speak Question</button>',
            '    <button id="bill-observation-voice" style="background:#1d4ed8;color:#eff6ff;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;">Speak Answer</button>',
            '    <label style="font-size:12px;color:#cbd5e1;display:flex;align-items:center;gap:6px;">Frequency',
            '      <select id="bill-observation-frequency" style="background:#0f172a;color:#f8fafc;border:1px solid rgba(148,163,184,0.35);border-radius:8px;padding:4px 8px;">',
            '        <option value="low">Low</option>',
            '        <option value="medium">Medium</option>',
            '        <option value="high">High</option>',
            '      </select>',
            '    </label>',
            '  </div>',
            '  <div style="display:flex;gap:8px;flex-wrap:wrap;">',
            '    <button id="bill-observation-submit" style="background:#10b981;color:#042f1a;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;font-weight:600;">Save Answer</button>',
            '    <button id="bill-observation-known" style="background:#f59e0b;color:#1f2937;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;">Mark Step Known</button>',
            '    <button id="bill-observation-later" style="background:#334155;color:#e2e8f0;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;">Answer Later</button>',
            '    <button id="bill-observation-skip" style="background:#475569;color:#e2e8f0;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;">Skip</button>',
            '    <button id="bill-observation-skip-all" style="background:#7f1d1d;color:#fee2e2;border:none;border-radius:999px;padding:8px 12px;cursor:pointer;">Skip All</button>',
            '  </div>',
            '  <div id="bill-observation-status" style="font-size:12px;color:#93c5fd;min-height:18px;"></div>',
            '</div>'
        ].join('');
        document.body.appendChild(panel);

        var state = {
            activePrompt: null,
            promptQueue: [],
            paused: false,
            skipAll: false,
            frequency: 'medium',
            responseMode: 'text',
            recognition: null,
            listening: false,
            speakingQuestion: false
        };

        var els = {
            panel: panel,
            trigger: panel.querySelector('#bill-observation-trigger'),
            question: panel.querySelector('#bill-observation-question'),
            context: panel.querySelector('#bill-observation-context'),
            answer: panel.querySelector('#bill-observation-answer'),
            status: panel.querySelector('#bill-observation-status'),
            pause: panel.querySelector('#bill-observation-pause'),
            speakQuestion: panel.querySelector('#bill-observation-speak-question'),
            voice: panel.querySelector('#bill-observation-voice'),
            submit: panel.querySelector('#bill-observation-submit'),
            known: panel.querySelector('#bill-observation-known'),
            later: panel.querySelector('#bill-observation-later'),
            skip: panel.querySelector('#bill-observation-skip'),
            skipAll: panel.querySelector('#bill-observation-skip-all'),
            frequency: panel.querySelector('#bill-observation-frequency')
        };

        function updateStatus(text) {
            els.status.textContent = text || '';
        }

        function renderPrompt(prompt) {
            state.activePrompt = prompt || null;
            if (state.skipAll) {
                els.panel.style.display = 'block';
                els.trigger.textContent = 'questions skipped';
                els.question.textContent = 'Observation questions are skipped for this session.';
                els.context.textContent = '';
                els.answer.value = '';
                updateStatus('Click Pause to resume questions later if needed.');
                return;
            }
            els.panel.style.display = 'block';
            if (!prompt) {
                els.trigger.textContent = 'observation mode';
                els.question.textContent = 'Bill is observing your workflow. Questions will appear as you work.';
                els.context.textContent = window.location.href || '';
                els.answer.value = '';
                updateStatus('Continue the workflow. You can type notes anytime.');
                return;
            }
            var category = String(prompt.category || '').replace(/_/g, ' ');
            var trigger = String(prompt.trigger_type || '').replace(/_/g, ' ');
            els.trigger.textContent = category ? (category + ' - ' + trigger) : trigger;
            els.question.textContent = prompt.question || 'What are you checking here?';
            var systemName = (prompt.system_context || {}).system || (prompt.system_context || {}).host || '';
            var pathName = (prompt.system_context || {}).path || '';
            els.context.textContent = [systemName, pathName].filter(Boolean).join(' | ');
            els.answer.value = '';
            state.responseMode = 'text';
            updateStatus(state.paused ? 'Questions are paused for this session.' : 'You can answer, skip, or come back later.');
        }

        function showNextPrompt() {
            if (state.paused || state.skipAll) {
                renderPrompt(null);
                return;
            }
            if (state.activePrompt) {
                renderPrompt(state.activePrompt);
                return;
            }
            if (!state.promptQueue.length) {
                renderPrompt(null);
                return;
            }
            renderPrompt(state.promptQueue.shift());
        }

        async function speakCurrentQuestion() {
            updateStatus('Question voice is handled by the dashboard ElevenLabs provider.');
        }

        function emitAnswer(action) {
            if (!state.activePrompt) { return; }
            emit({
                event_type: 'observation_answer',
                prompt_id: state.activePrompt.prompt_id,
                step_order: state.activePrompt.step_order,
                action: action,
                answer: els.answer.value || '',
                response_mode: action === 'answer' ? state.responseMode : 'control',
                question_type: state.activePrompt.question_type,
                trigger_type: state.activePrompt.trigger_type,
                question_frequency: els.frequency.value,
                system_context: state.activePrompt.system_context || {},
                url: window.location.href,
                ts: Date.now()
            });
            if (action !== 'pause' && action !== 'resume' && action !== 'set_frequency') {
                state.activePrompt = null;
                showNextPrompt();
            }
        }

        function applySettings(settings) {
            settings = settings || {};
            if (settings.observation_question_frequency) {
                state.frequency = settings.observation_question_frequency;
                els.frequency.value = state.frequency;
            }
            state.paused = !!settings.observation_questions_paused;
            state.skipAll = !!settings.observation_skip_all_questions;
            els.pause.textContent = state.paused ? 'Resume' : 'Pause';
            if (state.skipAll) {
                updateStatus('Skip all questions is enabled.');
                els.panel.style.display = 'none';
                return;
            }
            if (state.paused) {
                updateStatus('Questions are paused.');
            }
        }

        function startVoiceCapture() {
            var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            if (!SpeechRecognition) {
                updateStatus('Speech capture is not supported in this browser.');
                return;
            }
            if (state.listening && state.recognition) {
                try { state.recognition.stop(); } catch (err) { }
                return;
            }
            var recognition = new SpeechRecognition();
            state.recognition = recognition;
            recognition.lang = 'en-US';
            recognition.interimResults = true;
            recognition.continuous = false;
            recognition.onstart = function () {
                state.listening = true;
                els.voice.textContent = 'Stop Listening';
                updateStatus('Listening for your answer...');
            };
            recognition.onresult = function (event) {
                var transcript = '';
                for (var i = event.resultIndex; i < event.results.length; i++) {
                    transcript += event.results[i][0].transcript;
                }
                els.answer.value = transcript.trim();
                state.responseMode = 'voice';
                updateStatus('Voice answer captured. You can edit it before saving.');
            };
            recognition.onerror = function () {
                updateStatus('Voice capture failed. Type your answer instead.');
            };
            recognition.onend = function () {
                state.listening = false;
                els.voice.textContent = 'Speak Answer';
            };
            recognition.start();
        }

        els.submit.addEventListener('click', function () { emitAnswer('answer'); });
        els.skip.addEventListener('click', function () { emitAnswer('skip'); });
        els.later.addEventListener('click', function () { emitAnswer('later'); });
        els.known.addEventListener('click', function () { emitAnswer('known'); });
        els.skipAll.addEventListener('click', function () {
            state.skipAll = true;
            emitAnswer('skip_all');
        });
        els.pause.addEventListener('click', function () {
            state.paused = !state.paused;
            emitAnswer(state.paused ? 'pause' : 'resume');
            if (!state.paused) { showNextPrompt(); }
        });
        els.frequency.addEventListener('change', function () {
            emit({
                event_type: 'observation_answer',
                prompt_id: state.activePrompt ? state.activePrompt.prompt_id : '',
                step_order: state.activePrompt ? state.activePrompt.step_order : 0,
                action: 'set_frequency',
                answer: '',
                response_mode: 'control',
                question_type: state.activePrompt ? state.activePrompt.question_type : '',
                trigger_type: state.activePrompt ? state.activePrompt.trigger_type : '',
                question_frequency: els.frequency.value,
                system_context: state.activePrompt ? (state.activePrompt.system_context || {}) : {},
                url: window.location.href,
                ts: Date.now()
            });
            updateStatus('Question frequency updated to ' + els.frequency.value + '.');
        });
        els.speakQuestion.addEventListener('click', function () { void speakCurrentQuestion(); });
        els.voice.addEventListener('click', startVoiceCapture);

        window.__billObservationPanel = {
            showPrompt: function (prompt, settings) {
                applySettings(settings || {});
                if (!prompt || state.skipAll) { return; }
                if (state.activePrompt) {
                    state.promptQueue.push(prompt);
                    updateStatus('Queued another observation question.');
                    return;
                }
                renderPrompt(prompt);
            },
            applySettings: applySettings,
            hide: function () {
                state.activePrompt = null;
                els.panel.style.display = 'none';
            }
        };

        renderPrompt(null);

        return window.__billObservationPanel;
    }

    function ensurePanelEventually() {
        if (ensureQuestionPanel()) { return; }
        setTimeout(ensurePanelEventually, 250);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', ensurePanelEventually, { once: true });
    } else {
        ensurePanelEventually();
    }

    emit({event_type: '_attached', url: window.location.href});
}());
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _label(element: dict[str, Any]) -> str:
    return (
        element.get("aria_label")
        or element.get("text")
        or element.get("placeholder")
        or element.get("name")
        or element.get("id")
        or ""
    ).strip()[:60]


def _infer_step_name(event: dict[str, Any]) -> str:
    et = event.get("event_type", "")
    el = event.get("element") or {}
    lbl = _label(el)
    url = event.get("url", "")
    opt = event.get("option_text", "") or event.get("value", "")

    if et == "navigate":
        try:
            path = urlparse(url).path.rstrip("/") or "/"
            return f"Navigate → {path[:60]}"
        except Exception:
            return f"Navigate → {url[:60]}"
    if et == "click":
        return f"Click '{lbl}'" if lbl else "Click element"
    if et == "type_text":
        return f"Fill '{lbl}'" if lbl else "Enter text"
    if et == "select_option":
        return (f"Select '{opt}'" + (f" in '{lbl}'" if lbl else "")) if opt else "Select option"
    return "Perform action"


def _infer_intent(event: dict[str, Any]) -> str:
    et = event.get("event_type", "")
    lbl = _label(event.get("element") or {})
    if et == "navigate":
        return "Navigate to the required page."
    if et == "click":
        return f"Trigger the next step by clicking '{lbl}'." if lbl else "Advance the workflow."
    if et == "type_text":
        return f"Supply required data into '{lbl}'." if lbl else "Provide required input."
    if et == "select_option":
        return f"Set the required option for '{lbl}'." if lbl else "Choose the required dropdown value."
    return ""


_ACTION_MAP = {
    "navigate":      "open_url",
    "click":         "click_selector",
    "type_text":     "type_text",
    "select_option": "select_option",
}


def _event_to_step(event: dict[str, Any]) -> dict[str, Any]:
    et = event.get("event_type", "")
    el = event.get("element") or {}
    url = event.get("url", "")
    parsed = urlparse(url) if url else None
    return {
        "action":        _ACTION_MAP.get(et, et),
        "step_name":     _infer_step_name(event),
        "intent":        _infer_intent(event),
        "description":   _infer_step_name(event),
        "selector":      event.get("selector", ""),
        "url":           event.get("url", "") if et == "navigate" else "",
        "value":         event.get("value", ""),
        "option":        event.get("option_text", ""),
        "element_label": _label(el),
        "element_tag":   el.get("tag", ""),
        "element_type":  el.get("input_type", ""),
        "event_type":    et,
        "system_context": {
            "url": url,
            "host": parsed.netloc if parsed else "",
            "path": parsed.path if parsed else "",
            "system": (parsed.netloc.split(':')[0] if parsed and parsed.netloc else ""),
            "element_label": _label(el),
            "element_tag": el.get("tag", ""),
            "element_type": el.get("input_type", ""),
        },
        "captured_at":   datetime.now(timezone.utc).isoformat(),
    }


def _post_step(api_base: str, draft_id: str, step: dict[str, Any]) -> dict[str, Any] | None:
    endpoint = f"{api_base.rstrip('/')}/api/brain/workflow-learning/drafts/{draft_id}/steps/append"
    try:
        resp = requests.post(endpoint, json=step, timeout=APPEND_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [teach] Append failed ({resp.status_code}): {resp.text[:120]}", file=sys.stderr)
    except Exception as exc:
        print(f"  [teach] HTTP error: {exc}", file=sys.stderr)
    return None


def _post_observation_answer(api_base: str, draft_id: str, answer_payload: dict[str, Any]) -> dict[str, Any] | None:
    endpoint = f"{api_base.rstrip('/')}/api/brain/workflow-learning/drafts/{draft_id}/observation/answer"
    try:
        resp = requests.post(endpoint, json=answer_payload, timeout=APPEND_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
        print(f"  [teach] Observation answer failed ({resp.status_code}): {resp.text[:120]}", file=sys.stderr)
    except Exception as exc:
        print(f"  [teach] Observation HTTP error: {exc}", file=sys.stderr)
    return None


def _event_to_browser_action(event: dict[str, Any]) -> dict[str, Any]:
    et = str(event.get("event_type") or "")
    action_type = "click"
    if et == "type_text":
        action_type = "type"
    elif et == "navigate":
        action_type = "navigate"
    elif et == "select_option":
        action_type = "select"
    elif et == "submit":
        action_type = "submit"

    el = event.get("element") or {}
    label = _label(el)
    selector = event.get("selector") or ""
    sensitive_terms = ("password", "ssn", "code", "token", "mfa", "dob", "phone", "email")
    label_selector_text = f"{label} {selector}".lower()
    looks_sensitive = any(term in label_selector_text for term in sensitive_terms)

    return {
        "id": str(uuid4()),
        "type": action_type,
        "selector": None if looks_sensitive else (selector or None),
        "label": "[sensitive]" if looks_sensitive and label else (label or None),
        "value_redacted": "[redacted]" if action_type == "type" or looks_sensitive else None,
        "url": event.get("url") or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _post_teaching_action(api_base: str, session_id: str, action_payload: dict[str, Any]) -> bool:
    if not session_id:
        return False
    endpoint = f"{api_base.rstrip('/')}/api/teaching/session/{session_id}/actions"
    try:
        resp = requests.post(endpoint, json={"action": action_payload}, timeout=APPEND_TIMEOUT)
        if resp.status_code == 200:
            return True
        print(f"  [teach] Action capture failed ({resp.status_code}): {resp.text[:120]}", file=sys.stderr)
    except Exception as exc:
        print(f"  [teach] Action capture HTTP error: {exc}", file=sys.stderr)
    return False


def _post_teaching_context(api_base: str, session_id: str, context_payload: dict[str, Any]) -> tuple[bool, str | None]:
    if not session_id:
        return False, "missing session_id"
    endpoint = f"{api_base.rstrip('/')}/api/teaching/session/{session_id}/context"
    try:
        resp = requests.post(endpoint, json=context_payload, timeout=APPEND_TIMEOUT)
        if resp.status_code == 200:
            return True, None
        return False, f"HTTP {resp.status_code}: {resp.text[:120]}"
    except Exception as exc:
        return False, str(exc)


def _clip_text(value: Any, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[:max_len]
    return text


def _detect_sensitive_field(label: str, placeholder: str, name: str, input_type: str) -> bool:
    lowered = f"{label} {placeholder} {name} {input_type}".lower()
    terms = (
        "password",
        "mfa",
        "otp",
        "code",
        "token",
        "secret",
        "ssn",
        "social",
        "dob",
        "birth",
        "phone",
        "email",
    )
    return any(term in lowered for term in terms)


def _build_page_context_snapshot(page: Any, reason: str, recent_clicked: dict | None, recent_typed_field: str | None, page_changed: bool) -> dict[str, Any] | None:
    try:
        raw = page.evaluate(
            """
            () => {
                function clip(s, n=120) {
                    const t = String(s || '').replace(/\\s+/g, ' ').trim();
                    return t.length > n ? t.slice(0, n) : t;
                }
                function visible(el) {
                    if (!el) return false;
                    const r = el.getBoundingClientRect();
                    if (!r || r.width <= 0 || r.height <= 0) return false;
                    const st = window.getComputedStyle(el);
                    return st && st.visibility !== 'hidden' && st.display !== 'none';
                }
                function selectorHint(el) {
                    if (!el) return null;
                    if (el.id) return '#' + String(el.id).replace(/[^\\w-]/g, '_');
                    const name = el.getAttribute('name');
                    if (name) return `${el.tagName.toLowerCase()}[name="${clip(name, 50)}"]`;
                    const aria = el.getAttribute('aria-label');
                    if (aria) return `${el.tagName.toLowerCase()}[aria-label="${clip(aria, 50)}"]`;
                    return el.tagName.toLowerCase();
                }

                const buttons = [];
                for (const el of Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]'))) {
                    if (!visible(el)) continue;
                    if (buttons.length >= 20) break;
                    buttons.push({
                        text: clip(el.innerText || el.textContent || el.value || ''),
                        aria_label: clip(el.getAttribute('aria-label') || ''),
                        role: clip(el.getAttribute('role') || (el.tagName || '').toLowerCase()),
                        selector_hint: selectorHint(el),
                    });
                }

                const inputs = [];
                for (const el of Array.from(document.querySelectorAll('input, textarea, select'))) {
                    if (!visible(el)) continue;
                    if (inputs.length >= 20) break;
                    const inputType = String(el.getAttribute('type') || (el.tagName || '').toLowerCase()).toLowerCase();
                    let labelText = '';
                    const id = el.id;
                    if (id) {
                        const label = document.querySelector(`label[for="${id}"]`);
                        if (label) labelText = clip(label.innerText || label.textContent || '');
                    }
                    if (!labelText) {
                        const parentLabel = el.closest('label');
                        if (parentLabel) labelText = clip(parentLabel.innerText || parentLabel.textContent || '');
                    }
                    inputs.push({
                        label: labelText,
                        placeholder: clip(el.getAttribute('placeholder') || ''),
                        type: clip(inputType),
                        name: clip(el.getAttribute('name') || ''),
                        selector_hint: selectorHint(el),
                    });
                }

                const links = [];
                for (const el of Array.from(document.querySelectorAll('a[href]'))) {
                    if (!visible(el)) continue;
                    if (links.length >= 20) break;
                    links.push({
                        text: clip(el.innerText || el.textContent || ''),
                        href: clip(el.getAttribute('href') || ''),
                    });
                }

                const headings = [];
                for (const el of Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6'))) {
                    if (!visible(el)) continue;
                    if (headings.length >= 10) break;
                    const level = Number(String(el.tagName || '').replace('H', '')) || null;
                    headings.push({ text: clip(el.innerText || el.textContent || ''), level });
                }

                const active = document.activeElement;
                const activeEl = active && active !== document.body ? {
                    type: clip((active.tagName || '').toLowerCase()),
                    label: clip(active.getAttribute('aria-label') || active.getAttribute('name') || active.getAttribute('placeholder') || active.innerText || active.textContent || ''),
                } : null;

                let modalEl = document.querySelector('[role="dialog"], [aria-modal="true"], .modal, .popup');
                if (modalEl && !visible(modalEl)) modalEl = null;
                const modalSummary = modalEl ? {
                    present: true,
                    title: clip(modalEl.getAttribute('aria-label') || (modalEl.querySelector('h1,h2,h3')?.textContent) || ''),
                    text: clip(modalEl.textContent || ''),
                } : { present: false, title: '', text: '' };

                return {
                    url: window.location.href,
                    title: clip(document.title || ''),
                    visible_buttons: buttons,
                    visible_inputs: inputs,
                    visible_links: links,
                    visible_headings: headings,
                    active_element: activeEl,
                    modal_summary: modalSummary,
                    modal_present: !!modalSummary.present,
                    modal_title: modalSummary.title || null,
                };
            }
            """
        )
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    visible_inputs = []
    for inp in list(raw.get("visible_inputs") or [])[:20]:
        label = _clip_text(inp.get("label") or "")
        placeholder = _clip_text(inp.get("placeholder") or "")
        input_type = _clip_text(inp.get("type") or "text")
        name = _clip_text(inp.get("name") or "")
        sensitive = _detect_sensitive_field(label, placeholder, name, input_type)
        visible_inputs.append(
            {
                "label": "[redacted]" if sensitive else label,
                "placeholder": "[redacted]" if sensitive else placeholder,
                "type": input_type,
                "name": "[redacted]" if sensitive else name,
                "selector_hint": None if sensitive else _clip_text(inp.get("selector_hint") or "") or None,
                "sensitive": sensitive,
            }
        )

    snapshot = {
        "url": _clip_text(raw.get("url") or ""),
        "title": _clip_text(raw.get("title") or ""),
        "visible_buttons": list(raw.get("visible_buttons") or [])[:20],
        "visible_inputs": visible_inputs,
        "visible_links": list(raw.get("visible_links") or [])[:20],
        "visible_headings": list(raw.get("visible_headings") or [])[:10],
        "active_element": raw.get("active_element") or None,
        "recent_clicked_element": recent_clicked or None,
        "recent_typed_field": _clip_text(recent_typed_field or "") or None,
        "modal_summary": raw.get("modal_summary") or {"present": False, "title": "", "text": ""},
        "modal_present": bool(raw.get("modal_present")),
        "modal_title": _clip_text(raw.get("modal_title") or "") or None,
        "page_changed": bool(page_changed),
        "reason": _clip_text(reason, 40),
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    return snapshot


def _load_observation_settings(api_base: str) -> dict[str, Any]:
    endpoint = f"{api_base.rstrip('/')}/api/brain/preferences"
    settings = {
        "observation_question_frequency": "medium",
        "observation_questions_paused": False,
        "observation_skip_all_questions": False,
    }
    try:
        resp = requests.get(endpoint, timeout=APPEND_TIMEOUT)
        if resp.status_code != 200:
            return settings
        for item in resp.json() or []:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "")
            value = item.get("value")
            if key == "observation.question_frequency" and value in {"low", "medium", "high"}:
                settings["observation_question_frequency"] = value
            elif key == "observation.pause_questions":
                settings["observation_questions_paused"] = bool(value)
            elif key == "observation.skip_all_questions":
                settings["observation_skip_all_questions"] = bool(value)
    except Exception:
        return settings
    return settings


def _extract_observation_prompt(result: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if not isinstance(result, dict):
        return None, {
            "observation_question_frequency": "medium",
            "observation_questions_paused": False,
            "observation_skip_all_questions": False,
        }
    settings = {
        "observation_question_frequency": str(result.get("observation_question_frequency") or "medium"),
        "observation_questions_paused": bool(result.get("observation_questions_paused", False)),
        "observation_skip_all_questions": bool(result.get("observation_skip_all_questions", False)),
    }
    steps = result.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return None, settings
    last_step = steps[-1] if isinstance(steps[-1], dict) else {}
    for prompt in (last_step.get("observation_questions") or []):
        if isinstance(prompt, dict) and str(prompt.get("status") or "pending") == "pending":
            return prompt, settings
    return None, settings


def _detect_chrome_path() -> Path:
    candidates = [
        os.getenv("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise FileNotFoundError("Google Chrome executable not found")


def _is_debug_chrome_ready(port: int) -> bool:
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
        return resp.ok and bool(resp.text)
    except Exception:
        return False


def _wait_for_debug_chrome(port: int, timeout_seconds: float = 12.0) -> bool:
    started = time.monotonic()
    while time.monotonic() - started < timeout_seconds:
        if _is_debug_chrome_ready(port):
            return True
        time.sleep(0.3)
    return False


# ── Session runner ────────────────────────────────────────────────────────────

def run_session(
    draft_id: str,
    api_base: str,
    start_url: str | None = None,
    session_id: str | None = None,
    chrome_user_data_dir: str | None = None,
    profile_directory: str = "Default",
    remote_debugging_port: int = 9222,
    on_browser_ready: "Callable[[], None] | None" = None,
) -> dict[str, Any]:
    sep = "=" * 62
    print(f"\n{sep}")
    print(f"  Bill Teach Mode — Observation Session")
    print(sep)
    print(f"  Draft    : {draft_id}")
    print(f"  API base : {api_base}")
    if start_url:
        print(f"  Start URL: {start_url}")
    print()
    print(f"  Perform your workflow in the browser.")
    print(f"  Clicks, text entry, and navigation are captured automatically.")
    print(f"  Password fields are never recorded.")
    print(f"  Close the browser window when finished.\n")

    last_event_ts: dict[str, float] = {}
    last_url: list[str] = [""]
    recent_clicked_element: dict | None = None
    recent_typed_field: str | None = None
    step_num: list[int] = [0]
    step_lock = threading.Lock()
    user_data_dir = Path(chrome_user_data_dir or (Path.home() / "AppData" / "Local" / "BillCore" / "ChromeProfiles" / "BillTeaching")).resolve()
    launch_command = (
        f"chrome --remote-debugging-port={remote_debugging_port} "
        f"--user-data-dir={user_data_dir} "
        f"--profile-directory={profile_directory} --start-maximized"
    )
    browser_launch_succeeded = False
    observation_settings = _load_observation_settings(api_base)

    # ── Background thread drains HTTP posts so Playwright's event
    #    loop is never blocked by a slow/failed HTTP request. ──────
    post_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
    ui_queue: queue.Queue[dict[str, Any]] = queue.Queue()

    def _post_worker() -> None:
        while True:
            item = post_queue.get()
            if item is None:        # sentinel → shut down
                post_queue.task_done()
                break
            kind = str(item.get("kind") or "step") if isinstance(item, dict) else "step"
            if kind == "observation_answer":
                result = _post_observation_answer(api_base, draft_id, dict(item.get("data") or {}))
                if result is not None:
                    ui_queue.put({"type": "apply_settings", "settings": result})
                    print(f"  [obs ] {result.get('status', 'saved')} -> prompt {item.get('data', {}).get('prompt_id', '?')}")
            elif kind == "teaching_action":
                _post_teaching_action(api_base, str(session_id or ""), dict(item.get("data") or {}))
            elif kind == "context":
                ok, err = _post_teaching_context(api_base, str(session_id or ""), dict(item.get("data") or {}))
                if not ok:
                    ui_queue.put(
                        {
                            "type": "context_warning",
                            "message": "Bill may not have the latest page view. Continue, or repeat the action.",
                            "detail": err or "unknown error",
                        }
                    )
            else:
                step = dict(item.get("data") or {})
                result = _post_step(api_base, draft_id, step)
                if result is not None:
                    with step_lock:
                        step_num[0] += 1
                        n = step_num[0]
                    name  = step.get("step_name", "?")
                    action = step.get("action", "?")
                    print(f"  [{n:>3}] {action:<22} -> {name}")
                    prompt, settings = _extract_observation_prompt(result)
                    ui_queue.put({"type": "apply_settings", "settings": settings})
                    if prompt is not None:
                        ui_queue.put({"type": "show_prompt", "prompt": prompt, "settings": settings})
            post_queue.task_done()

    worker = threading.Thread(target=_post_worker, daemon=True)
    worker.start()

    def _enqueue_step(step: dict[str, Any]) -> None:
        post_queue.put({"kind": "step", "data": step})

    def _enqueue_observation_answer(answer_event: dict[str, Any]) -> None:
        post_queue.put({"kind": "observation_answer", "data": answer_event})

    def _enqueue_teaching_action(action_payload: dict[str, Any]) -> None:
        if not session_id:
            return
        post_queue.put({"kind": "teaching_action", "data": action_payload})

    def _enqueue_context(context_payload: dict[str, Any]) -> None:
        if not session_id:
            return
        post_queue.put({"kind": "context", "data": context_payload})

    def _current_primary_page() -> Any:
        for existing in context.pages:
            if not existing.is_closed():
                return existing
        return page

    def _capture_context(reason: str, page_changed: bool = False) -> None:
        target_page = _current_primary_page()
        snapshot = _build_page_context_snapshot(
            target_page,
            reason=reason,
            recent_clicked=recent_clicked_element,
            recent_typed_field=recent_typed_field,
            page_changed=page_changed,
        )
        if snapshot is None:
            return
        _enqueue_context(snapshot)

    def record(event: dict[str, Any]) -> None:
        nonlocal recent_clicked_element, recent_typed_field
        et = event.get("event_type", "")
        if et == "_attached":
            print(f"  [listen] Attached on {event.get('url', '?')}")
            return
        if et == "observation_answer":
            _enqueue_observation_answer(
                {
                    "prompt_id": event.get("prompt_id", ""),
                    "step_order": int(event.get("step_order") or 0),
                    "action": event.get("action", "answer"),
                    "answer": event.get("answer", ""),
                    "response_mode": event.get("response_mode", "text"),
                    "question_type": event.get("question_type", ""),
                    "trigger_type": event.get("trigger_type", ""),
                    "question_frequency": event.get("question_frequency"),
                    "system_context": event.get("system_context") or {},
                }
            )
            return
        now = time.monotonic()
        if now - last_event_ts.get(et, 0.0) < EVENT_DEBOUNCE:
            return
        last_event_ts[et] = now
        element = event.get("element") or {}
        if et == "click":
            recent_clicked_element = {
                "text": _clip_text(element.get("text") or element.get("aria_label") or element.get("name") or ""),
                "role": _clip_text(element.get("role") or element.get("tag") or ""),
            }
        elif et in {"type_text", "select_option"}:
            recent_typed_field = _clip_text(
                element.get("aria_label")
                or element.get("name")
                or element.get("placeholder")
                or ""
            )
        _enqueue_teaching_action(_event_to_browser_action(event))
        _enqueue_step(_event_to_step(event))
        if et in {"click", "type_text", "select_option", "submit"}:
            _capture_context(reason=et, page_changed=False)

    def on_navigate(url: str) -> None:
        if url == last_url[0]:
            return
        if url.startswith(("about:", "chrome:", "data:", "javascript:")):
            return
        last_url[0] = url
        last_event_ts["navigate"] = time.monotonic()
        nav_event = {"event_type": "navigate", "url": url, "element": {}}
        _enqueue_teaching_action(_event_to_browser_action(nav_event))
        _enqueue_step(_event_to_step(nav_event))
        _capture_context(reason="navigation", page_changed=True)

    def attach_page(p: Any) -> None:
        p.on("framenavigated", lambda frame: on_navigate(frame.url) if frame == p.main_frame else None)

    def _drain_frames() -> None:
        """Poll every frame in every open page and drain their window.__billEvents.

        JS pushes events into window.__billEvents (a per-frame array).
        frame.evaluate() reads and clears the array atomically from Python.
        This bypasses console.log overrides, CSP, and cross-origin iframe
        restrictions that defeated the previous console.log / CDP approaches.
        """
        try:
            for p in context.pages:
                if p.is_closed():
                    continue
                for frame in p.frames:
                    try:
                        events = frame.evaluate(
                            "() => { var e = window.__billEvents || []; "
                            "window.__billEvents = []; return e; }"
                        )
                        for evt in (events or []):
                            et = evt.get("event_type", "?")
                            if et != "_attached":
                                print(f"  [evt ] received: {et}")
                            record(evt)
                    except Exception:
                        pass
        except Exception:
            pass

    def _apply_observation_settings_to_pages(settings: dict[str, Any]) -> None:
        try:
            for p in context.pages:
                if p.is_closed():
                    continue
                try:
                    p.evaluate(
                        "(settings) => { if (window.__billObservationPanel) { window.__billObservationPanel.applySettings(settings); } }",
                        settings,
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _show_prompt_on_pages(prompt: dict[str, Any], settings: dict[str, Any]) -> None:
        try:
            for p in context.pages:
                if p.is_closed():
                    continue
                try:
                    p.evaluate(
                        "(payload) => { if (window.__billObservationPanel) { window.__billObservationPanel.showPrompt(payload.prompt, payload.settings); } }",
                        {"prompt": prompt, "settings": settings},
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def _drain_ui_updates() -> None:
        while True:
            try:
                update = ui_queue.get_nowait()
            except queue.Empty:
                break
            update_type = str(update.get("type") or "")
            if update_type == "apply_settings":
                observation_settings.update(dict(update.get("settings") or {}))
                _apply_observation_settings_to_pages(observation_settings)
            elif update_type == "show_prompt":
                prompt = dict(update.get("prompt") or {})
                settings = dict(update.get("settings") or observation_settings)
                observation_settings.update(settings)
                _show_prompt_on_pages(prompt, observation_settings)
            elif update_type == "context_warning":
                message = str(update.get("message") or "")
                detail = str(update.get("detail") or "")
                try:
                    for p in context.pages:
                        if p.is_closed():
                            continue
                        p.evaluate(
                            "(payload) => { const status = document.querySelector('#bill-observation-status'); if (status) { status.textContent = payload.message; status.style.color = '#fca5a5'; status.title = payload.detail || ''; } }",
                            {"message": message, "detail": detail},
                        )
                except Exception:
                    pass

    with sync_playwright() as pw:
        print(f"  [teach] final Chrome launch command: {launch_command}")
        try:
            user_data_dir.mkdir(parents=True, exist_ok=True)
            if not _is_debug_chrome_ready(remote_debugging_port):
                chrome_path = _detect_chrome_path()
                chrome_args = [
                    str(chrome_path),
                    f"--remote-debugging-port={remote_debugging_port}",
                    f"--user-data-dir={str(user_data_dir)}",
                    f"--profile-directory={profile_directory}",
                    "--start-maximized",
                    "--no-first-run",
                    "--no-default-browser-check",
                ]
                if start_url:
                    chrome_args.append(start_url)
                subprocess.Popen(chrome_args)

            if not _wait_for_debug_chrome(remote_debugging_port):
                raise RuntimeError(f"Chrome debug endpoint unavailable on 127.0.0.1:{remote_debugging_port}")

            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{remote_debugging_port}")
        except Exception as exc:
            print(f"  [teach] browser launch succeeded: False ({exc})", file=sys.stderr)
            raise RuntimeError(f"Unable to launch Chromium for teach session: {exc}") from exc

        context = browser.contexts[0] if browser.contexts else browser.new_context(viewport=None)
        context.add_init_script(f"window.__billTeachApiBase = {json.dumps(api_base.rstrip('/'))};")
        context.add_init_script(_LISTENER_JS)

        page = context.pages[0] if context.pages else context.new_page()
        browser_launch_succeeded = True
        print("  [teach] browser launch succeeded: True")
        if on_browser_ready is not None:
            try:
                on_browser_ready()
            except Exception as _cb_exc:
                print(f"  [teach] on_browser_ready callback error (non-fatal): {_cb_exc}", file=sys.stderr)
        attach_page(page)
        _apply_observation_settings_to_pages(observation_settings)

        def on_new_page(new_page: Any) -> None:
            """Attach listeners to pages opened by the workflow (new tabs etc.)."""
            try:
                attach_page(new_page)
            except Exception:
                pass

        context.on("page", on_new_page)

        if start_url:
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
                _capture_context(reason="page_load", page_changed=True)
            except Exception as exc:
                print(f"  [teach] Could not load start URL: {exc}", file=sys.stderr)
        else:
            _capture_context(reason="page_load", page_changed=True)

        try:
            while browser.is_connected():
                _drain_frames()
                _drain_ui_updates()
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("\n  [teach] Interrupted.")
        finally:
            try:
                browser.close()
            except Exception:
                pass
            # Drain remaining queued steps before exiting
            post_queue.put(None)
            worker.join(timeout=30)

    with step_lock:
        total = step_num[0]
    print(f"\n  Session complete. {total} steps captured.")
    print(f"  Open the Bill dashboard to review, enrich, and publish the draft.\n")
    return {
        "status": "completed",
        "draft_id": draft_id,
        "api_base": api_base,
        "start_url": start_url or "",
        "final_chrome_launch_command": launch_command,
        "browser_launch_succeeded": browser_launch_succeeded,
        "steps_captured": total,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bill Teach Mode — Playwright observation browser"
    )
    parser.add_argument("--draft-id", required=True, help="Workflow learning draft ID")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE, help="Bill Core API base URL")
    parser.add_argument("--start-url", default=None, help="Optional URL to open when the browser launches")
    parser.add_argument("--chrome-user-data-dir", default=None, help="Chrome --user-data-dir path")
    parser.add_argument("--profile-directory", default="Default", help="Chrome --profile-directory value")
    parser.add_argument("--remote-debugging-port", type=int, default=9222, help="Chrome remote debugging port")
    args = parser.parse_args()
    run_session(
        args.draft_id,
        args.api_base,
        args.start_url,
        chrome_user_data_dir=args.chrome_user_data_dir,
        profile_directory=args.profile_directory,
        remote_debugging_port=args.remote_debugging_port,
    )


if __name__ == "__main__":
    main()
