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
        [--api-base http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com] \
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
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

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
DEFAULT_API_BASE = (
    os.getenv("BILL_CORE_URL")
    or os.getenv("JARVIS_CORE_URL")
    or "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
).rstrip("/")
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


# ── Session runner ────────────────────────────────────────────────────────────

def run_session(draft_id: str, api_base: str, start_url: str | None = None) -> None:
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
    step_num: list[int] = [0]
    step_lock = threading.Lock()
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

    def record(event: dict[str, Any]) -> None:
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
        _enqueue_step(_event_to_step(event))

    def on_navigate(url: str) -> None:
        if url == last_url[0]:
            return
        if url.startswith(("about:", "chrome:", "data:", "javascript:")):
            return
        last_url[0] = url
        last_event_ts["navigate"] = time.monotonic()
        _enqueue_step(_event_to_step({"event_type": "navigate", "url": url, "element": {}}))

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

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--start-maximized", "--disable-infobars"],
        )
        context = browser.new_context(viewport=None)
        context.add_init_script(f"window.__billTeachApiBase = {json.dumps(api_base.rstrip('/'))};")
        context.add_init_script(_LISTENER_JS)

        page = context.new_page()
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
            except Exception as exc:
                print(f"  [teach] Could not load start URL: {exc}", file=sys.stderr)

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


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bill Teach Mode — Playwright observation browser"
    )
    parser.add_argument("--draft-id", required=True, help="Workflow learning draft ID")
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help="Bill Core API base URL (production defaults to Beanstalk; use localhost only for local dev)",
    )
    parser.add_argument("--start-url", default=None, help="Optional URL to open when the browser launches")
    args = parser.parse_args()
    run_session(args.draft_id, args.api_base, args.start_url)


if __name__ == "__main__":
    main()
