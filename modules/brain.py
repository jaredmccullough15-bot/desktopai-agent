# modules/brain.py
from __future__ import annotations

import base64
import json
import os
import re
import time
from urllib.parse import quote_plus, urlparse
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Third-party / UI
import pyautogui

# OpenAI SDK
from openai import OpenAI

# Local modules
from .vision import get_active_window_info, capture_active_window_png_bytes
from .actions import open_app_and_type, focus_app_and_type, save_active_file, open_url, open_url_and_click_result, fill_login_fields, open_url_and_fill_login, cycle_browser_tab
from .memory import get_memory_notes, find_password_entry, list_password_entries, list_password_entry_summaries
from .memory import find_web_link

load_dotenv()

# --- OpenAI client ---
# Requires OPENAI_API_KEY in your environment (.env is fine)
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
client: Optional[OpenAI] = OpenAI(api_key=_OPENAI_API_KEY) if _OPENAI_API_KEY else None


# -----------------------------
# Helpers
# -----------------------------

def _now_ts() -> float:
    return time.time()


def _strip_code_fences(text: str) -> str:
    """
    Removes ```json ... ``` or ``` ... ``` fences if the model returns them.
    """
    if not text:
        return text
    text = text.strip()
    # Remove leading/trailing triple backtick blocks
    if text.startswith("```"):
        # Remove first fence line
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        # Remove trailing fence
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _safe_json_loads(text: str) -> Optional[dict]:
    """
    Try to parse JSON. Returns None if it fails.
    """
    try:
        return json.loads(text)
    except Exception:
        return None


def _local_fallback_action(user_text: str) -> Optional[dict]:
    """
    Basic local fallback for simple commands when model fails.
    Supports: open notepad; open notepad and type "...".
    """
    if not user_text:
        return None

    raw_text = user_text.strip()
    text = raw_text.lower()

    # Pattern: open notepad and type "..." or unquoted text
    m = re.search(r"open\s+(?:note\s*pad|notepad|notebook)\s+and\s+type\s+[\"\u201c\u201d](.+?)[\"\u201c\u201d]", raw_text, re.IGNORECASE)
    if m:
        typed = m.group(1).strip()
        return {"type": "open_app_and_type", "app_name": "notepad", "text": typed}

    m2 = re.search(r"open\s+(?:note\s*pad|notepad|notebook)\s+and\s+type\s+(.+)$", raw_text, re.IGNORECASE)
    if m2:
        typed = m2.group(1).strip()
        return {"type": "open_app_and_type", "app_name": "notepad", "text": typed}

    # Pattern: open notepad
    if re.search(r"\bopen\s+(?:note\s*pad|notepad|notebook)\b", text, re.IGNORECASE):
        return {"type": "open_app_and_type", "app_name": "notepad", "text": ""}

    # Pattern: type into the notepad you just opened
    m3 = re.search(r"type\s+into\s+the\s+notepad\s+you\s+just\s+opened\s+[\"\u201c\u201d](.+?)[\"\u201c\u201d]", raw_text, re.IGNORECASE)
    if m3:
        typed = m3.group(1).strip()
        return {"type": "focus_app_and_type", "app_name": "notepad", "text": typed}

    m4 = re.search(r"type\s+into\s+the\s+notepad\s+you\s+just\s+opened\s+(.+)$", raw_text, re.IGNORECASE)
    if m4:
        typed = m4.group(1).strip()
        return {"type": "focus_app_and_type", "app_name": "notepad", "text": typed}

    # Pattern: save the notepad to the desktop with the name X
    m5 = re.search(r"save\s+the\s+notepad\s+to\s+the\s+desktop\s+with\s+the\s+name\s+[\"\u201c\u201d](.+?)[\"\u201c\u201d]", raw_text, re.IGNORECASE)
    if m5:
        filename = m5.group(1).strip()
        return {"type": "save_active_file", "filename": filename}

    m6 = re.search(r"save\s+the\s+notepad\s+to\s+the\s+desktop\s+with\s+the\s+name\s+(.+)$", raw_text, re.IGNORECASE)
    if m6:
        filename = m6.group(1).strip()
        return {"type": "save_active_file", "filename": filename}

    return None


def _build_system_prompt() -> str:
    """
    System instructions for the model. Keep it strict: return JSON only.
    """
    return (
        "You are a desktop automation assistant.\n"
        "You will be given:\n"
        "- The user's instruction\n"
        "- Active window metadata\n"
        "- A screenshot (as an image)\n\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "thought": string,\n'
        '  "answer": string,\n'
        '  "action": null | {\n'
        '    "type": "open_app_and_type" | "focus_app_and_type" | "save_active_file" | "open_url" | "open_url_and_click_result" | "fill_login_from_passwords" | "open_url_and_fill_login" | "browser_tab_next" | "browser_tab_prev",\n'
        '    "app_name": string,\n'
        '    "text": string,\n'
        '    "filename": string,\n'
        '    "url": string,\n'
        '    "match_text": string,\n'
        '    "label": string,\n'
        '    "submit": boolean\n'
        "  },\n"
        '  "actions": null | [action]\n'
        "}\n\n"
        "Rules:\n"
        "- Output JSON only (no markdown, no code fences).\n"
        "- If no action is needed, set action to null.\n"
        "- If you only need to open an app, set text to an empty string.\n"
        "- For websites or searches, use action.type=\"open_url\" and set url (use https://).\n"
        "- To click a result by title, use action.type=\"open_url_and_click_result\" with url and match_text.\n"
        "- To fill a login form from stored Passwords, use action.type=\"fill_login_from_passwords\" with label or url, and set submit=true to click/login.\n"
        "- If you need to open a login page and fill credentials, prefer action.type=\"open_url_and_fill_login\" with url and label, and set submit=true.\n"
        "- Never iterate through password entries. Only use the specific label or url explicitly requested by the user.\n"
        "- For tasks inside the current website/tab, do NOT use open_app_and_type; use focus_app_and_type with app_name set to the browser.\n"
        "- Never use open_app_and_type with app_name set to 'browser'.\n"
        "- If a URL matches a stored password entry, the system may auto-fill credentials for that site.\n"
        "- If multiple steps are required, use the actions array in order.\n"
        "- Always respond to the user’s instruction directly. Do not invent tasks.\n"
        "- Never open or interact with unrelated apps (games, updates, etc.). Only perform steps explicitly requested or defined in a process_doc.\n"
        "- If a process_doc is provided, follow it strictly and do not add extra steps.\n"
        "- Do NOT type passwords directly; use fill_login_from_passwords instead.\n"
        "- If the user is greeting or sharing info, reply conversationally and set action to null.\n"
        "- If MEMORY_NOTES include a process_doc and the user asks to follow it, convert each step into concrete actions.\n"
        "- Tone: optimistic, friendly, smooth, and proactive.\n"
        "- Be careful: do not hallucinate UI state.\n"
    )


def _normalize_browser_action(action: dict) -> Optional[dict]:
    """
    Convert browser open-and-type into a direct open_url action when possible.
    """
    if not isinstance(action, dict):
        return None
    if action.get("type") != "open_app_and_type":
        return None

    app_name = str(action.get("app_name", "")).strip().lower()
    text = str(action.get("text", "")).strip()
    if not text:
        return None

    if app_name not in {"microsoft edge", "edge", "google chrome", "chrome"}:
        return None

    lowered = text.lower()
    if "youtube" in lowered:
        return {"type": "open_url", "url": "https://www.youtube.com"}

    # If text looks like a domain, open it directly
    if "." in text and " " not in text:
        return {"type": "open_url", "url": text}

    # Otherwise do a search
    return {"type": "open_url", "url": f"https://www.google.com/search?q={quote_plus(text)}"}


def _normalize_web_action(action: dict) -> Optional[dict]:
    """
    Convert focus/open app actions that target websites into open_url actions.
    """
    if not isinstance(action, dict):
        return None
    action_type = action.get("type")
    if action_type not in {"open_app_and_type", "focus_app_and_type"}:
        return None

    app_name = str(action.get("app_name", "")).strip().lower()
    text = str(action.get("text", "")).strip()

    if app_name in {"youtube", "you tube", "www.youtube.com"}:
        if text:
            return {
                "type": "open_url_and_click_result",
                "url": f"https://www.youtube.com/results?search_query={quote_plus(text)}",
                "match_text": text,
            }
        return {"type": "open_url", "url": "https://www.youtube.com"}

    return None


def _call_openai(user_text: str, window_info: dict, screenshot_png: Optional[bytes], memory_notes: Optional[list] = None) -> Dict[str, Any]:
    """
    Calls OpenAI and returns a dict:
    {
      ok: bool,
      model_text: str,
      parsed: dict|None,
      error: str|None
    }
    """
    if client is None:
        return {
            "ok": False,
            "model_text": "",
            "parsed": None,
            "error": "OPENAI_API_KEY is not set. Add it to your .env or environment variables.",
        }

    system_prompt = _build_system_prompt()
    memory_block = ""
    if memory_notes:
        memory_block = f"MEMORY_NOTES (recent):\n{json.dumps(memory_notes, ensure_ascii=False)}\n\n"

    password_summaries = list_password_entry_summaries()
    password_block = ""
    if password_summaries:
        password_block = f"PASSWORD_ENTRIES (label, url, username):\n{json.dumps(password_summaries, ensure_ascii=False)}\n\n"

    user_payload = (
        f"USER_INSTRUCTION:\n{user_text}\n\n"
        f"{memory_block}"
        f"{password_block}"
        f"ACTIVE_WINDOW_INFO (JSON):\n{json.dumps(window_info, ensure_ascii=False)}\n"
    )

    content = [{"type": "input_text", "text": user_payload}]

    if screenshot_png:
        b64 = base64.b64encode(screenshot_png).decode("utf-8")
        content.append({"type": "input_image", "image_url": f"data:image/png;base64,{b64}"})
    else:
        content.append({"type": "input_text", "text": "SCREENSHOT: null\n"})

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        resp = client.responses.create(
            model=model_name,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": content},
            ],
            temperature=0.2,
            max_output_tokens=800,
        )

        text = (resp.output_text or "").strip()
        text = _strip_code_fences(text)
        parsed = _safe_json_loads(text)

        error = None
        if not text:
            error = "Empty response from model."

        return {
            "ok": True,
            "model_text": text,
            "parsed": parsed,
            "error": error,
        }

    except Exception as e:
        return {
            "ok": False,
            "model_text": "",
            "parsed": None,
            "error": f"OpenAI call failed: {type(e).__name__}: {e}",
        }


def _maybe_execute_action(action: Optional[dict]) -> Dict[str, Any]:
    """
    Executes a supported action dict.
    Returns an execution result dict.
    """
    if not action:
        return {"executed": False, "result": None, "error": None}

    if not isinstance(action, dict):
        return {"executed": False, "result": None, "error": "Action is not a dict."}

    action_type = action.get("type")
    if action_type not in {"open_app_and_type", "focus_app_and_type", "save_active_file", "open_url", "open_url_and_click_result", "fill_login_from_passwords", "open_url_and_fill_login", "browser_tab_next", "browser_tab_prev"}:
        return {"executed": False, "result": None, "error": f"Unsupported action type: {action_type!r}"}

    app_name = str(action.get("app_name", "")).strip()
    text = str(action.get("text", "")).strip()
    filename = str(action.get("filename", "")).strip()
    url = str(action.get("url", "")).strip()
    match_text = str(action.get("match_text", "")).strip()
    label = str(action.get("label", "")).strip()
    if action_type in {"fill_login_from_passwords", "open_url_and_fill_login"}:
        submit = bool(action.get("submit", True))
    else:
        submit = bool(action.get("submit", False))
    if action_type in {"open_app_and_type", "focus_app_and_type"} and not app_name:
        return {"executed": False, "result": None, "error": "Missing action.app_name"}
    if action_type in {"open_app_and_type", "focus_app_and_type"}:
        if re.search(r"\bsolitaire\b", app_name, re.IGNORECASE):
            return {"executed": False, "result": None, "error": "Blocked unrelated app: solitaire"}
        if re.search(r"\b(cmd|command\s*prompt|powershell|terminal)\b", app_name, re.IGNORECASE):
            return {"executed": False, "result": None, "error": "Blocked terminal app."}
    if action_type == "save_active_file" and not filename:
        return {"executed": False, "result": None, "error": "Missing action.filename"}
    if action_type == "open_url" and not url:
        return {"executed": False, "result": None, "error": "Missing action.url"}
    if action_type == "open_url_and_click_result" and not url:
        return {"executed": False, "result": None, "error": "Missing action.url"}
    if action_type == "open_url_and_fill_login" and not url:
        return {"executed": False, "result": None, "error": "Missing action.url"}

    try:
        # Uses your existing helper
        if action_type == "open_app_and_type":
            normalized = _normalize_browser_action(action)
            if normalized:
                action_type = normalized.get("type")
                action = {**action, **normalized}
                url = str(action.get("url", "")).strip()
                if url:
                    open_url(url)
                    return {"executed": True, "result": {"type": "open_url", "url": url}, "error": None}
            normalized = _normalize_web_action(action)
            if normalized:
                norm_type = normalized.get("type")
                url = str(normalized.get("url", "")).strip()
                match_text = str(normalized.get("match_text", "")).strip()
                if url and norm_type == "open_url":
                    open_url(url)
                    return {"executed": True, "result": {"type": "open_url", "url": url}, "error": None}
                if url and norm_type == "open_url_and_click_result":
                    open_url_and_click_result(url, match_text if match_text else None)
                    return {"executed": True, "result": {"type": "open_url_and_click_result", "url": url, "match_text": match_text}, "error": None}
            open_app_and_type(app_name, text if text else None)
            return {"executed": True, "result": {"type": action_type, "app_name": app_name}, "error": None}
        if action_type == "focus_app_and_type":
            normalized = _normalize_web_action(action)
            if normalized:
                norm_type = normalized.get("type")
                url = str(normalized.get("url", "")).strip()
                match_text = str(normalized.get("match_text", "")).strip()
                if url and norm_type == "open_url":
                    open_url(url)
                    return {"executed": True, "result": {"type": "open_url", "url": url}, "error": None}
                if url and norm_type == "open_url_and_click_result":
                    open_url_and_click_result(url, match_text if match_text else None)
                    return {"executed": True, "result": {"type": "open_url_and_click_result", "url": url, "match_text": match_text}, "error": None}
            focus_app_and_type(app_name, text if text else None)
            return {"executed": True, "result": {"type": action_type, "app_name": app_name}, "error": None}
        if action_type == "save_active_file":
            save_active_file(filename)
            return {"executed": True, "result": {"type": action_type, "filename": filename}, "error": None}
        if action_type == "open_url":
            open_url(url)
            return {"executed": True, "result": {"type": action_type, "url": url}, "error": None}
        if action_type == "open_url_and_click_result":
            ok = open_url_and_click_result(url, match_text if match_text else None)
            if not ok:
                return {"executed": False, "result": None, "error": "Failed to click matching result."}
            return {"executed": True, "result": {"type": action_type, "url": url, "match_text": match_text}, "error": None}
        if action_type == "fill_login_from_passwords":
            entry = find_password_entry(label=label or None, url=url or None)
            if not entry:
                return {"executed": False, "result": None, "error": "No matching password entry found."}
            username = entry.get("username")
            password = entry.get("password")
            ok = fill_login_fields(username, password, submit=submit)
            if not ok:
                return {"executed": False, "result": None, "error": "Failed to fill login fields."}
            return {"executed": True, "result": {"type": action_type, "label": entry.get("label"), "url": entry.get("url"), "submit": submit}, "error": None}
        if action_type == "open_url_and_fill_login":
            entry = find_password_entry(label=label or None, url=url or None)
            if not entry:
                return {"executed": False, "result": None, "error": "No matching password entry found."}
            username = entry.get("username")
            password = entry.get("password")
            ok = open_url_and_fill_login(url, username, password, submit=submit)
            if not ok:
                return {"executed": False, "result": None, "error": "Failed to open page or fill login fields."}
            return {"executed": True, "result": {"type": action_type, "label": entry.get("label"), "url": url, "submit": submit}, "error": None}
        if action_type == "browser_tab_next":
            cycle_browser_tab("next")
            return {"executed": True, "result": {"type": action_type}, "error": None}
        if action_type == "browser_tab_prev":
            cycle_browser_tab("prev")
            return {"executed": True, "result": {"type": action_type}, "error": None}
    except Exception as e:
        return {"executed": False, "result": None, "error": f"Action failed: {type(e).__name__}: {e}"}


# -----------------------------
# Public API (what main.py imports)
# -----------------------------

def process_one_turn(user_text: str, *, execute_actions: bool = False) -> Dict[str, Any]:
    """
    Main entry point:
    - Collect window info + screenshot
    - Call OpenAI for a response JSON
    - Optionally execute action if execute_actions=True and model returns one

    Returns a structured dict safe to print/log.
    """
    start = _now_ts()

    # PyAutoGUI safety: prevent runaway by moving mouse to top-left corner
    pyautogui.FAILSAFE = True

    window_info = {}
    screenshot_png = None

    # Gather context (never hard-crash)
    try:
        window_info = get_active_window_info()
    except Exception as e:
        window_info = {"error": f"get_active_window_info failed: {type(e).__name__}: {e}"}

    try:
        screenshot_png = capture_active_window_png_bytes()
    except Exception as e:
        screenshot_png = None
        # annotate window_info instead of failing
        if isinstance(window_info, dict):
            window_info["screenshot_error"] = f"capture_active_window_png_bytes failed: {type(e).__name__}: {e}"

    max_steps = int(os.getenv("MAX_STEP_ACTIONS", "3"))
    exec_results = []

    model_result = None
    parsed = None
    action = None
    actions = None
    answer = None
    thought = None

    instruction = user_text

    # Quick web link shortcut: "go to X url"
    m = re.search(r"\bgo\s+to\s+(.+?)\s+url\b", user_text, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        link = find_web_link(name)
        if link:
            action = {"type": "open_url", "url": link.get("url")}
            exec_result = _maybe_execute_action(action) if execute_actions else {"executed": False, "result": None, "error": None}
            return {
                "ok": True,
                "timestamp": start,
                "elapsed_sec": round(_now_ts() - start, 3),
                "input": user_text,
                "active_window": window_info,
                "screenshot_bytes_len": len(screenshot_png) if screenshot_png else 0,
                "model": {
                    "used": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "raw_text": "",
                    "parsed_json": None,
                    "thought": None,
                    "answer": f"Opening {name}.",
                    "action": action,
                    "actions": None,
                    "error": None,
                },
                "execution": exec_result,
            }
    for step_idx in range(max_steps):
        memory_notes = get_memory_notes(limit=20)
        model_result = _call_openai(
            user_text=instruction,
            window_info=window_info,
            screenshot_png=screenshot_png,
            memory_notes=memory_notes,
        )

        parsed = model_result.get("parsed")
        action = None
        actions = None
        answer = None
        thought = None

        if isinstance(parsed, dict):
            thought = parsed.get("thought")
            answer = parsed.get("answer")
            action = parsed.get("action")
            actions = parsed.get("actions")

        if isinstance(action, dict):
            action = _coerce_web_focus_action(action, user_text, window_info)
        if isinstance(actions, list) and actions:
            actions = [_coerce_web_focus_action(a, user_text, window_info) for a in actions if isinstance(a, dict)]

        # Coalesce actions to avoid duplicate browser opens
        if isinstance(actions, list) and actions:
            has_click = any(a.get("type") == "open_url_and_click_result" for a in actions if isinstance(a, dict))
            if has_click:
                actions = [a for a in actions if not (isinstance(a, dict) and a.get("type") == "open_url")]

        if not answer and (action or actions):
            answer = "OK."

        # Fallback: only if explicitly enabled
        if os.getenv("ALLOW_LOCAL_FALLBACK", "0") == "1":
            if not action and not answer:
                fallback_action = _local_fallback_action(user_text)
                if fallback_action:
                    action = fallback_action
                    answer = f"Okay, opening {fallback_action.get('app_name')}."

        exec_result = {"executed": False, "result": None, "error": None}
        if execute_actions:
            password_entries = list_password_entry_summaries()
            password_target = _pick_password_target(user_text, password_entries)
            if isinstance(actions, list) and actions:
                if any(isinstance(a, dict) and a.get("type") == "open_url_and_click_result" for a in actions):
                    actions = [a for a in actions if not (isinstance(a, dict) and a.get("type") == "open_url")]
                filtered_actions = []
                for act in actions:
                    if not isinstance(act, dict):
                        continue
                    act_type = act.get("type")
                    act_url = str(act.get("url", "")).strip().lower()
                    if password_target:
                        target_url = str(password_target.get("url", "")).strip().lower()
                        target_domain = _extract_domain(target_url)
                        if act_type == "open_url" and act_url:
                            if act_url != target_url and _extract_domain(act_url) != target_domain:
                                continue
                        if act_type in {"fill_login_from_passwords", "open_url_and_fill_login"}:
                            act["label"] = password_target.get("label")
                            act["url"] = password_target.get("url")
                    else:
                        if act_type in {"fill_login_from_passwords", "open_url_and_fill_login"}:
                            if not act.get("label") and not act.get("url"):
                                continue
                    if act_type == "open_url" and act_url:
                        matches = [e for e in password_entries if str(e.get("url", "")).lower() == act_url]
                        if matches and not any(_password_matches_request(user_text, m) for m in matches):
                            continue
                    if act_type in {"fill_login_from_passwords", "open_url_and_fill_login"}:
                        if not act.get("label") and not act.get("url"):
                            continue
                    filtered_actions.append(act)
                if not filtered_actions:
                    exec_result = {"executed": False, "result": None, "error": "No password action matched your request."}
                else:
                    # De-dupe actions to avoid repeated opens
                    seen = set()
                    deduped = []
                    for act in filtered_actions:
                        key = (
                            act.get("type"),
                            str(act.get("url", "")).strip().lower(),
                            str(act.get("label", "")).strip().lower(),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        deduped.append(act)
                    actions = deduped
                results = []
                for act in actions:
                    results.append(_maybe_execute_action(act))
                exec_result = {"executed": True, "result": results, "error": None}
            elif isinstance(action, dict):
                if password_target:
                    target_url = str(password_target.get("url", "")).strip().lower()
                    target_domain = _extract_domain(target_url)
                    if action.get("type") == "open_url":
                        act_url = str(action.get("url", "")).strip().lower()
                        if act_url and act_url != target_url and _extract_domain(act_url) != target_domain:
                            exec_result = {"executed": False, "result": None, "error": "Password target does not match requested site."}
                            exec_results.append(exec_result)
                            break
                    if action.get("type") in {"fill_login_from_passwords", "open_url_and_fill_login"}:
                        action["label"] = password_target.get("label")
                        action["url"] = password_target.get("url")
                if action.get("type") == "open_url":
                    act_url = str(action.get("url", "")).strip().lower()
                    matches = [e for e in password_entries if str(e.get("url", "")).lower() == act_url]
                    if matches and not any(_password_matches_request(user_text, m) for m in matches):
                        exec_result = {"executed": False, "result": None, "error": "Password URL not explicitly requested."}
                        exec_results.append(exec_result)
                        break
                if action.get("type") in {"fill_login_from_passwords", "open_url_and_fill_login"}:
                    if not action.get("label") and not action.get("url"):
                        exec_result = {"executed": False, "result": None, "error": "Missing password label or url."}
                        exec_results.append(exec_result)
                        break
                exec_result = _maybe_execute_action(action)

        exec_results.append(exec_result)

        # Decide whether to continue with another step
        if not execute_actions:
            break

        # If actions list was provided, do not auto-continue
        if isinstance(actions, list) and actions:
            break

        has_more = isinstance(action, dict)
        multi_step_hint = re.search(r"\b(and|then|after|next|also)\b", user_text, re.IGNORECASE)
        if not has_more or not multi_step_hint:
            break

        # Refresh context before continuing
        try:
            window_info = get_active_window_info()
        except Exception as e:
            window_info = {"error": f"get_active_window_info failed: {type(e).__name__}: {e}"}

        try:
            screenshot_png = capture_active_window_png_bytes()
        except Exception as e:
            screenshot_png = None
            if isinstance(window_info, dict):
                window_info["screenshot_error"] = f"capture_active_window_png_bytes failed: {type(e).__name__}: {e}"

        instruction = f"Continue the task. Previous action result: {exec_result}."

    exec_result = exec_results[-1] if exec_results else {"executed": False, "result": None, "error": None}

    elapsed = _now_ts() - start
    if len(exec_results) > 1:
        exec_result = {"executed": True, "result": exec_results, "error": None}

    if isinstance(parsed, dict) and isinstance(answer, str):
        password_entries = list_password_entry_summaries()
        password_target = _pick_password_target(user_text, password_entries)
        if password_target:
            other_labels = [e.get("label") for e in password_entries if e.get("label") and e.get("label") != password_target.get("label")]
            for label in other_labels:
                if label and label in answer:
                    answer = f"Working on {password_target.get('label')}."
                    break

    return {
        "ok": bool(model_result.get("ok")),
        "timestamp": start,
        "elapsed_sec": round(elapsed, 3),
        "input": user_text,
        "active_window": window_info,
        "screenshot_bytes_len": len(screenshot_png) if screenshot_png else 0,
        "model": {
            "used": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "raw_text": model_result.get("model_text", ""),
            "parsed_json": parsed if isinstance(parsed, dict) else None,
            "thought": thought,
            "answer": answer,
            "action": action,
            "actions": actions,
            "error": model_result.get("error"),
        },
        "execution": exec_result,
    }


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.netloc or "").lower()
    except Exception:
        return ""


def _password_matches_request(user_text: str, entry: dict) -> bool:
    text = (user_text or "").lower()
    label = str(entry.get("label") or "").lower()
    url = str(entry.get("url") or "").lower()
    domain = _extract_domain(url)
    return (label and label in text) or (url and url in text) or (domain and domain in text)


def _find_password_for_url(url: str) -> Optional[dict]:
    normalized = (url or "").strip().lower()
    if not normalized:
        return None
    for entry in list_password_entries():
        entry_url = str(entry.get("url") or "").strip().lower()
        if not entry_url:
            continue
        if normalized == entry_url or normalized.startswith(entry_url):
            return entry
        if _extract_domain(normalized) and _extract_domain(normalized) == _extract_domain(entry_url):
            return entry
    return None


def _maybe_upgrade_to_login_action(action: dict) -> dict:
    if not isinstance(action, dict):
        return action
    if action.get("type") != "open_url":
        return action
    if os.getenv("AUTO_PASSWORDS", "1") != "1":
        return action
    url = str(action.get("url", "")).strip()
    entry = _find_password_for_url(url)
    if not entry:
        return action
    return {
        "type": "open_url_and_fill_login",
        "url": entry.get("url") or url,
        "label": entry.get("label"),
        "submit": True,
    }


def _coerce_web_focus_action(action: dict, user_text: str, window_info: dict) -> dict:
    if not isinstance(action, dict):
        return action
    if action.get("type") not in {"open_app_and_type", "focus_app_and_type"}:
        return action

    app_name = str(action.get("app_name", "")).strip().lower()
    if app_name in {"chrome", "google chrome", "edge", "microsoft edge"}:
        return action

    text = (user_text or "").lower()
    title = (window_info.get("title") if isinstance(window_info, dict) else "") or ""
    title = title.lower()
    if any(k in text for k in ["current browser", "current website", "current tab", "in the website", "in the browser", "trackvia", "in trackvia", "after login"]):
        browser = "chrome" if "chrome" in title else "edge" if "edge" in title else "chrome"
        return {"type": "focus_app_and_type", "app_name": browser, "text": action.get("text", "")}

    if app_name in {"browser", ""} and ("chrome" in title or "edge" in title):
        browser = "chrome" if "chrome" in title else "edge"
        return {"type": "focus_app_and_type", "app_name": browser, "text": action.get("text", "")}

    return action


def _pick_password_target(user_text: str, entries: list) -> Optional[dict]:
    if not entries:
        return None
    matches = [e for e in entries if _password_matches_request(user_text, e)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        # If multiple match, prefer label match over domain/url
        lowered = (user_text or "").lower()
        for e in matches:
            label = str(e.get("label") or "").lower()
            if label and label in lowered:
                return e
        return matches[0]
    return None
