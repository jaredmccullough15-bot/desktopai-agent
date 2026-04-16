# modules/brain.py
from __future__ import annotations

import base64
import json
import os
import re
import time
from urllib import request as urlrequest, error as urlerror
from urllib.parse import quote_plus, urlparse
from typing import Any, Dict, Optional

from dotenv import load_dotenv

# Third-party / UI
import pyautogui

# OpenAI SDK
from openai import OpenAI

# Local modules
from .vision import get_active_window_info, capture_active_window_png_bytes
from .actions import open_app_and_type, focus_app_and_type, save_active_file, open_url, open_url_and_click_result, fill_login_fields, open_url_and_fill_login, cycle_browser_tab, wait_for_page_load, search_page_for_identifier, close_current_tab, click_element_by_text, click_next_view_button, reset_view_button_counter, wait_for_element_with_text
from .memory import get_memory_notes, find_password_entry, list_password_entries, list_password_entry_summaries
from .memory import find_web_link, get_learning_patterns
from .conversation import get_conversation_memory
from .failure_learning import get_failure_system
from .integrations import list_integrations, call_api, send_webhook
from .notifications.outlook_notifier import send_assistance_email
from .excel_worker import run_excel_sheet_task
try:
    from .carriers.ambetter_worker import AmbetterWorker
except Exception:
    AmbetterWorker = None
try:
    from .carriers.priority_health_worker import PriorityHealthWorker
except Exception:
    PriorityHealthWorker = None

load_dotenv()

_LAST_AIRTABLE_LOOKUP: Dict[str, Any] = {
    "searched_names": [],
    "records": [],
    "pending_name": "",
    "pending_options": [],
    "pending_detail": {},
}

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


def _humanize_assistant_answer(user_text: str, answer: str, planned_actions: Optional[list] = None) -> str:
    text = (answer or "").strip()
    prompt = (user_text or "").strip()
    actions = planned_actions if isinstance(planned_actions, list) else []

    if not text:
        if actions:
            return "Absolutely — I’m on it now."
        return "Absolutely — happy to help."

    lower = text.lower()
    if text in {"OK.", "Ok.", "ok", "okay"}:
        return "Absolutely — I’m on it."

    if lower in {
        "hello! i'm jarvis, your personal assistant. how can i help you today?",
        "hello! i am jarvis, your personal assistant. how can i help you today?",
    }:
        return "Hey — I’m here and ready. What do you want to tackle first?"

    if actions and not any(p in lower for p in ["i'll", "i will", "i’m", "i am", "let me", "working on"]):
        return f"Got it — {text}"

    if len(text) < 28 and not text.endswith((".", "!", "?")):
        return text + "."

    return text


def _safe_json_loads(text: str) -> Optional[dict]:
    """
    Try to parse JSON. Returns None if it fails.
    """
    try:
        return json.loads(text)
    except Exception:
        return None


def _normalize_person_name(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip())
    return cleaned.casefold()


def _extract_airtable_client_names(user_text: str) -> list:
    text = (user_text or "").strip()
    lowered = text.lower()
    if not text:
        return []
    if "airtable" not in lowered:
        return []
    if not any(token in lowered for token in ["client", "clients", "named", "name", "check", "find", "search", "lookup"]):
        return []

    segment = text
    m = re.search(r"(?:named|name|for)\s+(.+)$", text, re.IGNORECASE)
    if m:
        segment = m.group(1)

    segment = re.split(r"\b(?:in airtable|from airtable|on airtable)\b", segment, maxsplit=1, flags=re.IGNORECASE)[0]
    segment = re.sub(r"^(?:clients?|records?)\s+named\s+", "", segment, flags=re.IGNORECASE)
    segment = segment.strip(" .,!?")
    if not segment:
        return []

    raw_parts = [p.strip(" .,!?") for p in re.split(r"\s*(?:,| and | & )\s*", segment, flags=re.IGNORECASE) if p.strip()]
    blocked = {"a client", "client", "clients", "someone", "them", "it"}
    names = []
    seen = set()
    for part in raw_parts:
        if part.lower() in blocked:
            continue
        if len(part.split()) > 5:
            continue
        key = _normalize_person_name(part)
        if not key or key in seen:
            continue
        seen.add(key)
        names.append(part)
    return names


def _extract_ambetter_member_request(user_text: str) -> Optional[Dict[str, str]]:
    text = (user_text or "").strip()
    lowered = text.lower()
    if not text or "ambetter" not in lowered:
        return None
    if not any(token in lowered for token in ["policy", "check", "lookup", "search", "find"]):
        return None

    member: Dict[str, str] = {
        "first_name": "",
        "last_name": "",
        "dob": "",
        "member_id": "",
        "policy_id": "",
    }

    m_dob = re.search(r"\bdob\b\s*[:\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", text, re.IGNORECASE)
    if m_dob:
        member["dob"] = m_dob.group(1).strip()

    m_member = re.search(r"\bmember\s*id\b\s*[:#-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m_member:
        member["member_id"] = m_member.group(1).strip()

    m_policy = re.search(r"\bpolicy\s*id\b\s*[:#-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m_policy:
        member["policy_id"] = m_policy.group(1).strip()

    m_name = re.search(r"\bfor\s+([A-Za-z][A-Za-z'\-]+)\s+([A-Za-z][A-Za-z'\-]+)", text, re.IGNORECASE)
    if m_name:
        member["first_name"] = m_name.group(1).strip()
        member["last_name"] = m_name.group(2).strip()

    if not any(member.values()):
        return None
    return member


def _extract_priority_health_member_request(user_text: str) -> Optional[Dict[str, str]]:
    text = (user_text or "").strip()
    lowered = text.lower()
    if not text or "priority health" not in lowered:
        return None
    if not any(token in lowered for token in ["policy", "check", "lookup", "search", "find", "member", "client"]):
        return None

    member: Dict[str, str] = {
        "first_name": "",
        "last_name": "",
        "dob": "",
        "member_id": "",
        "policy_id": "",
    }

    m_dob = re.search(r"\bdob\b\s*[:\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", text, re.IGNORECASE)
    if m_dob:
        member["dob"] = m_dob.group(1).strip()

    m_member = re.search(r"\bmember\s*id\b\s*[:#-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m_member:
        member["member_id"] = m_member.group(1).strip()

    m_policy = re.search(r"\bpolicy\s*id\b\s*[:#-]?\s*([A-Za-z0-9\-]+)", text, re.IGNORECASE)
    if m_policy:
        member["policy_id"] = m_policy.group(1).strip()

    m_name = re.search(r"\bfor\s+([A-Za-z][A-Za-z'\-]+)\s+([A-Za-z][A-Za-z'\-]+)", text, re.IGNORECASE)
    if m_name:
        member["first_name"] = m_name.group(1).strip()
        member["last_name"] = m_name.group(2).strip()

    if not any(member.values()):
        return None
    return member


def _is_ambetter_export_request(user_text: str) -> bool:
    text = (user_text or "").strip().lower()
    if not text or "ambetter" not in text:
        return False
    has_export = any(token in text for token in ["export", "download", "csv"])
    has_target = any(token in text for token in ["client", "clients", "member", "members", "active members", "policies"])
    return has_export and has_target


def _is_excel_work_request(user_text: str) -> bool:
    text = (user_text or "").strip().lower()
    if not text:
        return False
    excel_hint = any(token in text for token in ["excel", "spreadsheet", "sheet", ".xlsx", ".csv", "workbook", "ambetter clients", "columns", "rows"])
    action_hint = any(token in text for token in ["sort", "filter", "clean", "remove duplicates", "dedupe", "save as", "save a copy", "organize", "rename column", "drop column", "keep columns", "fill blanks", "merge", "split"])
    return excel_hint and action_hint


def _extract_outlook_email_request(user_text: str) -> Optional[Dict[str, str]]:
    text = (user_text or "").strip()
    lowered = text.lower()
    if not text:
        return None
    if "email" not in lowered and "outlook" not in lowered:
        return None
    if not any(token in lowered for token in ["send", "email", "notify", "message"]):
        return None

    to_value = ""
    subject = "Jarvis notification"
    body = ""

    m_to = re.search(r"\bto\s+([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?:\s*,\s*[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})*)", text, re.IGNORECASE)
    if m_to:
        to_value = m_to.group(1).strip()

    m_subject = re.search(r"\b(?:subject|about)\s+['\"]?(.+?)['\"]?(?:\s+body\b|\s+message\b|$)", text, re.IGNORECASE)
    if m_subject:
        subject = m_subject.group(1).strip() or subject

    m_body = re.search(r"\b(?:body|message)\s+(.+)$", text, re.IGNORECASE)
    if m_body:
        body = m_body.group(1).strip()
    elif m_subject:
        body = f"{m_subject.group(1).strip()}"

    if not body:
        body = "Jarvis generated notification."

    if not to_value:
        return None

    return {
        "to": to_value,
        "subject": subject,
        "body": body,
    }


def _extract_airtable_details_from_record(record: dict) -> dict:
    fields = record.get("fields") if isinstance(record, dict) else {}
    fields = fields if isinstance(fields, dict) else {}
    notes = str(fields.get("Notes") or fields.get("client notes") or "")

    details = {
        "name": str(fields.get("Name") or "").strip(),
        "phone": "",
        "dob": "",
        "appointment_date": str(fields.get("Appt Date") or "").strip(),
        "appointment_time": str(fields.get("Appt Time") or "").strip(),
        "effective_date": "",
        "notes": notes.strip(),
        "client_type": str(fields.get("Client Type") or "").strip(),
    }

    for line in notes.splitlines():
        line_text = line.strip()
        lowered = line_text.lower()
        if not line_text:
            continue
        if "phone" in lowered and not details["phone"]:
            parts = line_text.split(":", 1)
            details["phone"] = parts[1].strip() if len(parts) > 1 else line_text
        if ("dob" in lowered or "date of birth" in lowered) and not details["dob"]:
            parts = line_text.split(":", 1)
            details["dob"] = parts[1].strip() if len(parts) > 1 else line_text
        if "effective date" in lowered and not details["effective_date"]:
            parts = line_text.split(":", 1)
            details["effective_date"] = parts[1].strip() if len(parts) > 1 else line_text

    return details


def _airtable_option_label(details: dict) -> str:
    appt = str(details.get("appointment_date") or "").strip()
    appt_time = str(details.get("appointment_time") or "").strip()
    effective = str(details.get("effective_date") or "").strip()
    client_type = str(details.get("client_type") or "").strip()
    bits = []
    if appt:
        bits.append(f"appt {appt}")
    if appt_time:
        bits.append(appt_time)
    if effective:
        bits.append(f"effective {effective}")
    if client_type:
        bits.append(client_type)
    if not bits:
        bits.append("no date markers")
    return " | ".join(bits)


def _extract_choice_index(text: str, max_count: int) -> Optional[int]:
    lowered = (text or "").lower()
    if max_count <= 0:
        return None
    if re.search(r"\b(first|1st|option\s*1|#1|one)\b", lowered):
        return 0
    if re.search(r"\b(second|2nd|option\s*2|#2|two)\b", lowered) and max_count >= 2:
        return 1
    if re.search(r"\b(third|3rd|option\s*3|#3|three)\b", lowered) and max_count >= 3:
        return 2
    if re.search(r"\b(last|latest|most recent|newest)\b", lowered):
        return max_count - 1
    m = re.search(r"\b(\d+)\b", lowered)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < max_count:
            return idx
    return None


def _extract_requested_airtable_fields(lowered: str) -> Dict[str, bool]:
    wants_all = any(k in lowered for k in ["all", "everything", "full", "all details"])
    wants_phone = wants_all or ("phone" in lowered)
    wants_dob = wants_all or ("dob" in lowered) or ("date of birth" in lowered)
    wants_appt = wants_all or ("appointment" in lowered) or ("appt" in lowered)
    wants_effective = wants_all or ("effective" in lowered)
    wants_notes = wants_all or ("notes" in lowered)
    return {
        "wants_all": wants_all,
        "wants_phone": wants_phone,
        "wants_dob": wants_dob,
        "wants_appt": wants_appt,
        "wants_effective": wants_effective,
        "wants_notes": wants_notes,
    }


def _maybe_answer_airtable_detail_request(user_text: str) -> Optional[str]:
    text = (user_text or "").strip()
    lowered = text.lower()
    records = _LAST_AIRTABLE_LOOKUP.get("records") if isinstance(_LAST_AIRTABLE_LOOKUP, dict) else []
    records = records if isinstance(records, list) else []
    if not records:
        return None

    pending_options = _LAST_AIRTABLE_LOOKUP.get("pending_options") if isinstance(_LAST_AIRTABLE_LOOKUP, dict) else []
    pending_options = pending_options if isinstance(pending_options, list) else []
    pending_name = str(_LAST_AIRTABLE_LOOKUP.get("pending_name") or "") if isinstance(_LAST_AIRTABLE_LOOKUP, dict) else ""
    pending_detail = _LAST_AIRTABLE_LOOKUP.get("pending_detail") if isinstance(_LAST_AIRTABLE_LOOKUP, dict) else {}
    pending_detail = pending_detail if isinstance(pending_detail, dict) else {}

    detail_intent = any(k in lowered for k in ["phone", "dob", "date of birth", "appointment", "appt", "effective", "notes", "details", "info", "information", "everything", "all"]) 
    if not detail_intent and not pending_options:
        return None

    details_list = [_extract_airtable_details_from_record(r) for r in records if isinstance(r, dict)]
    details_list = [d for d in details_list if d.get("name")]
    if not details_list:
        return None

    if pending_options:
        idx = _extract_choice_index(text, len(pending_options))
        if idx is None:
            for i, option in enumerate(pending_options):
                label = _airtable_option_label(option).lower()
                if label and label in lowered:
                    idx = i
                    break
        if idx is not None and 0 <= idx < len(pending_options):
            selected = pending_options[idx]
            _LAST_AIRTABLE_LOOKUP["pending_options"] = []
            _LAST_AIRTABLE_LOOKUP["pending_name"] = ""
            lowered = lowered or ""
            if not any(k in lowered for k in ["phone", "dob", "date of birth", "appointment", "appt", "effective", "notes", "details", "info", "information", "everything", "all"]):
                restored = []
                if pending_detail.get("wants_phone"):
                    restored.append("phone")
                if pending_detail.get("wants_dob"):
                    restored.append("dob")
                if pending_detail.get("wants_appt"):
                    restored.append("appointment")
                if pending_detail.get("wants_effective"):
                    restored.append("effective")
                if pending_detail.get("wants_notes"):
                    restored.append("notes")
                if restored:
                    lowered = lowered + " " + " ".join(restored)
            _LAST_AIRTABLE_LOOKUP["pending_detail"] = {}
        else:
            option_lines = []
            for i, option in enumerate(pending_options, start=1):
                option_lines.append(f"{i}) {_airtable_option_label(option)}")
            return f"I found multiple records for {pending_name}. Reply with 1, 2, or 3. Options: " + " ; ".join(option_lines)
    else:
        selected = None

    if selected is None:
        requested_name = ""
        for item in details_list:
            if item["name"].lower() in lowered:
                requested_name = item["name"]
                break
        if not requested_name:
            m_name = re.search(r"(?:for|about|on)\s+([a-zA-Z][a-zA-Z\s\.-]{1,60})$", text, re.IGNORECASE)
            if m_name:
                requested_name = m_name.group(1).strip(" .,!?")

        if requested_name:
            requested_key = _normalize_person_name(requested_name)
            matching = [d for d in details_list if _normalize_person_name(d.get("name")) == requested_key]
            if not matching:
                names = ", ".join(sorted({d["name"] for d in details_list})[:4])
                return f"I don't have {requested_name} in the last Airtable result. I currently have: {names}."
            if len(matching) > 1:
                _LAST_AIRTABLE_LOOKUP["pending_name"] = matching[0].get("name")
                _LAST_AIRTABLE_LOOKUP["pending_options"] = matching
                _LAST_AIRTABLE_LOOKUP["pending_detail"] = _extract_requested_airtable_fields(lowered)
                option_lines = []
                for i, option in enumerate(matching, start=1):
                    option_lines.append(f"{i}) {_airtable_option_label(option)}")
                return f"I found {len(matching)} records for {matching[0].get('name')}. Which one do you want? " + " ; ".join(option_lines)
            selected = matching[0]
        else:
            names = ", ".join(sorted({d["name"] for d in details_list})[:4])
            return f"I found multiple clients in the last Airtable result. Which one do you want details for: {names}?"

    wanted = _extract_requested_airtable_fields(lowered)
    wants_all = wanted.get("wants_all", False)
    wants_phone = wanted.get("wants_phone", False)
    wants_dob = wanted.get("wants_dob", False)
    wants_appt = wanted.get("wants_appt", False)
    wants_effective = wanted.get("wants_effective", False)
    wants_notes = wanted.get("wants_notes", False)
    if not any([wants_phone, wants_dob, wants_appt, wants_effective, wants_notes]):
        wants_phone = wants_dob = wants_appt = wants_effective = True

    parts = []
    if wants_phone and selected.get("phone"):
        parts.append(f"Phone: {selected['phone']}")
    if wants_dob and selected.get("dob"):
        parts.append(f"DOB: {selected['dob']}")
    if wants_appt and (selected.get("appointment_date") or selected.get("appointment_time")):
        appt = selected.get("appointment_date") or ""
        if selected.get("appointment_time"):
            appt = f"{appt} at {selected['appointment_time']}" if appt else selected["appointment_time"]
        parts.append(f"Appointment: {appt}")
    if wants_effective and selected.get("effective_date"):
        parts.append(f"Effective date: {selected['effective_date']}")
    if wants_notes and selected.get("notes"):
        compact_notes = selected["notes"].replace("\n", " | ")
        if len(compact_notes) > 240:
            compact_notes = compact_notes[:240] + "..."
        parts.append(f"Notes: {compact_notes}")

    if not parts:
        return f"I found {selected['name']}, but I don't see that specific detail in the saved Airtable fields."
    return f"{selected['name']} — " + "; ".join(parts)


def _extract_weather_location(user_text: str) -> str:
    text = (user_text or "").strip()
    if not text:
        return "Michigan"

    m = re.search(r"\b(?:in|for)\s+([a-zA-Z][a-zA-Z\s\.-]{1,40})", text, re.IGNORECASE)
    if not m:
        return "Michigan"

    location = m.group(1).strip(" .,-")
    return location or "Michigan"


def _fetch_weather_summary(location: str) -> Optional[str]:
    target = (location or "Michigan").strip()
    open_meteo = _fetch_weather_summary_open_meteo(target)
    if open_meteo:
        return open_meteo

    return _fetch_weather_summary_wttr(target)


def _fetch_weather_summary_open_meteo(location: str) -> Optional[str]:
    target = (location or "Michigan").strip()
    try:
        place = {}
        if target.strip().lower() == "michigan":
            lat = 42.7335
            lon = -84.5555
            display_location = "Michigan"
        else:
            geocode_target = target
            geocode_url = (
                f"https://geocoding-api.open-meteo.com/v1/search?name={quote_plus(geocode_target)}&count=1&language=en&format=json"
            )
            req_geo = urlrequest.Request(geocode_url, headers={"User-Agent": "Jarvis-Agent/1.0"})
            with urlrequest.urlopen(req_geo, timeout=8) as resp:
                geo_raw = resp.read().decode("utf-8", errors="replace")
            geo_payload = json.loads(geo_raw)
            results = geo_payload.get("results") or []
            if not isinstance(results, list) or not results:
                return None

            place = results[0] if isinstance(results[0], dict) else {}
            lat = place.get("latitude")
            lon = place.get("longitude")
            if lat is None or lon is None:
                return None

            city = str(place.get("name") or target).strip()
            region = str(place.get("admin1") or "").strip()
            display_location = f"{city}, {region}".strip(", ")

        forecast_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,apparent_temperature,weather_code"
            "&daily=temperature_2m_max,temperature_2m_min"
            "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
            "&timezone=auto&forecast_days=1"
        )
        req_forecast = urlrequest.Request(forecast_url, headers={"User-Agent": "Jarvis-Agent/1.0"})
        with urlrequest.urlopen(req_forecast, timeout=8) as resp:
            forecast_raw = resp.read().decode("utf-8", errors="replace")
        forecast_payload = json.loads(forecast_raw)

        current = forecast_payload.get("current") or {}
        daily = forecast_payload.get("daily") or {}
        temp_f = current.get("temperature_2m")
        feels_f = current.get("apparent_temperature")
        weather_code = current.get("weather_code")
        max_list = daily.get("temperature_2m_max") or []
        min_list = daily.get("temperature_2m_min") or []
        max_f = max_list[0] if isinstance(max_list, list) and max_list else None
        min_f = min_list[0] if isinstance(min_list, list) and min_list else None

        if temp_f is None:
            return None

        summary = f"Today in {display_location}: {round(float(temp_f))}°F"
        desc = _weather_code_to_text(weather_code)
        if desc:
            summary += f", {desc}"
        if max_f is not None and min_f is not None:
            summary += f". High {round(float(max_f))}°F, low {round(float(min_f))}°F"
        if feels_f is not None:
            summary += f", feels like {round(float(feels_f))}°F"
        summary += "."
        return summary
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
    except Exception:
        return None


def _fetch_weather_summary_wttr(location: str) -> Optional[str]:
    target = (location or "Michigan").strip()
    try:
        weather_url = f"https://wttr.in/{quote_plus(target)}?format=j1"
        req = urlrequest.Request(weather_url, headers={"User-Agent": "Jarvis-Agent/1.0"})
        with urlrequest.urlopen(req, timeout=8) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)

        current = ((payload.get("current_condition") or [{}])[0]) if isinstance(payload, dict) else {}
        today = ((payload.get("weather") or [{}])[0]) if isinstance(payload, dict) else {}

        temp_f = str(current.get("temp_F") or "?")
        feels_f = str(current.get("FeelsLikeF") or "?")
        max_f = str(today.get("maxtempF") or "?")
        min_f = str(today.get("mintempF") or "?")
        desc_list = current.get("weatherDesc") or []
        desc = ""
        if isinstance(desc_list, list) and desc_list:
            desc = str((desc_list[0] or {}).get("value") or "").strip()

        summary = f"Today in {target}: {temp_f}°F"
        if desc:
            summary += f", {desc}"
        summary += f". High {max_f}°F, low {min_f}°F, feels like {feels_f}°F."
        return summary
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, KeyError, ValueError):
        return None
    except Exception:
        return None


def _weather_code_to_text(code: Any) -> str:
    try:
        value = int(code)
    except Exception:
        return ""

    mapping = {
        0: "clear",
        1: "mainly clear",
        2: "partly cloudy",
        3: "overcast",
        45: "fog",
        48: "freezing fog",
        51: "light drizzle",
        53: "drizzle",
        55: "heavy drizzle",
        56: "light freezing drizzle",
        57: "freezing drizzle",
        61: "light rain",
        63: "rain",
        65: "heavy rain",
        66: "light freezing rain",
        67: "freezing rain",
        71: "light snow",
        73: "snow",
        75: "heavy snow",
        77: "snow grains",
        80: "light rain showers",
        81: "rain showers",
        82: "heavy rain showers",
        85: "light snow showers",
        86: "snow showers",
        95: "thunderstorm",
        96: "thunderstorm with hail",
        99: "severe thunderstorm with hail",
    }
    return mapping.get(value, "")


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


def _find_integration_by_query(name_query: str) -> Optional[dict]:
    query = (name_query or "").strip().lower()
    if not query:
        return None

    all_integrations = [i for i in list_integrations() if isinstance(i, dict)]
    if not all_integrations:
        return None

    for entry in all_integrations:
        iname = str(entry.get("name") or "").strip().lower()
        if iname and iname == query:
            return entry

    for entry in all_integrations:
        iname = str(entry.get("name") or "").strip().lower()
        if iname and (query in iname or iname in query):
            return entry

    if "ai submit" in query or "sales and submit" in query or "mihq" in query:
        for entry in all_integrations:
            iname = str(entry.get("name") or "").strip().lower()
            if "ai submit" in iname or "mihq" in iname:
                return entry

    return None


def _is_howto_question(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    patterns = [
        r"^how\s+do\s+i\b",
        r"^how\s+can\s+i\b",
        r"^what\s+is\b",
        r"^where\s+do\s+i\b",
        r"^where\s+can\s+i\b",
        r"^can\s+you\s+explain\b",
    ]
    return any(re.search(p, lowered) for p in patterns)


def _multi_step_local_actions(user_text: str) -> list:
    raw = (user_text or "").strip()
    if not raw:
        return []

    chunks = [c.strip() for c in re.split(r"\bthen\b", raw, flags=re.IGNORECASE) if c.strip()]
    if len(chunks) < 2:
        return []

    actions = []
    for chunk in chunks:
        action = _local_fallback_action(chunk)
        if not isinstance(action, dict):
            return []
        actions.append(action)
    return actions


def _local_instruction_shortcut(user_text: str) -> Optional[dict]:
    text = (user_text or "").strip()
    if not text:
        return None

    lowered = text.lower()

    outlook_email = _extract_outlook_email_request(text)
    if outlook_email:
        return {
            "answer": "Sending Outlook email now.",
            "actions": [
                {
                    "type": "send_outlook_email",
                    "email_to": outlook_email.get("to", ""),
                    "email_subject": outlook_email.get("subject", "Jarvis notification"),
                    "email_body": outlook_email.get("body", "Jarvis generated notification."),
                }
            ],
            "thought": "Local shortcut: send Outlook email tool.",
        }

    if "ambetter" in lowered and any(token in lowered for token in ["open", "go to", "login", "log in", "sign in"]):
        if not any(token in lowered for token in ["policy", "member", "dob", "member id", "policy id", "check"]):
            return {
                "answer": "Opening Ambetter portal and signing in now.",
                "actions": [
                    {
                        "type": "check_ambetter_policy",
                        "first_name": "",
                        "last_name": "",
                        "dob": "",
                        "member_id": "",
                        "policy_id": "",
                        "login_only": True,
                    }
                ],
                "thought": "Local shortcut: open Ambetter portal with login-only worker flow.",
            }

    if _is_ambetter_export_request(text):
        return {
            "answer": "Exporting the Ambetter clients CSV now.",
            "actions": [
                {
                    "type": "export_ambetter_clients_csv",
                }
            ],
            "thought": "Local shortcut: Ambetter clients CSV export.",
        }

    if _is_excel_work_request(text):
        return {
            "answer": "Working on the Excel file now and saving a new copy.",
            "actions": [
                {
                    "type": "work_excel_file",
                    "instruction": text,
                    "file_path": "",
                    "sheet_name": "",
                    "output_filename": "",
                }
            ],
            "thought": "Local shortcut: Excel file operation request.",
        }

    ambetter_member = _extract_ambetter_member_request(text)
    if ambetter_member:
        first_name = ambetter_member.get("first_name", "")
        last_name = ambetter_member.get("last_name", "")
        member_label = f"{first_name} {last_name}".strip() or "the member"
        return {
            "answer": f"Checking Ambetter policy for {member_label} now.",
            "actions": [
                {
                    "type": "check_ambetter_policy",
                    "first_name": first_name,
                    "last_name": last_name,
                    "dob": ambetter_member.get("dob", ""),
                    "member_id": ambetter_member.get("member_id", ""),
                    "policy_id": ambetter_member.get("policy_id", ""),
                }
            ],
            "thought": "Local shortcut: Ambetter policy check.",
        }

    priority_member = _extract_priority_health_member_request(text)
    if priority_member:
        first_name = priority_member.get("first_name", "")
        last_name = priority_member.get("last_name", "")
        member_label = f"{first_name} {last_name}".strip() or "the member"
        return {
            "answer": f"Checking Priority Health policy for {member_label} now.",
            "actions": [
                {
                    "type": "check_priority_health_policy",
                    "first_name": first_name,
                    "last_name": last_name,
                    "dob": priority_member.get("dob", ""),
                    "member_id": priority_member.get("member_id", ""),
                    "policy_id": priority_member.get("policy_id", ""),
                }
            ],
            "thought": "Local shortcut: Priority Health policy check.",
        }

    airtable_names = _extract_airtable_client_names(text)
    if airtable_names:
        table_id = os.getenv("AIRTABLE_DEFAULT_TABLE_ID", "tblaSejx38hois2uu").strip() or "tblaSejx38hois2uu"
        actions = []
        for person_name in airtable_names[:3]:
            safe_name = person_name.replace("'", "\\'")
            actions.append(
                {
                    "type": "call_integration_api",
                    "integration_name": "Airtable",
                    "method": "GET",
                    "path": f"{table_id}?filterByFormula={{Name}}='{safe_name}'",
                }
            )
        joined = ", ".join(airtable_names)
        return {
            "answer": f"Checking Airtable for: {joined}.",
            "actions": actions,
            "thought": "Local shortcut: Airtable client lookup by name.",
        }

    # Pattern: open URL then click element text
    m_open_click = re.search(
        r"open\s+(https?://\S+)\s+then\s+click\s+[\"'“”]?(.+?)[\"'“”]?$",
        text,
        re.IGNORECASE,
    )
    if m_open_click:
        url = m_open_click.group(1).strip()
        click_text = m_open_click.group(2).strip()
        return {
            "answer": f"Opening the page and clicking '{click_text}'.",
            "actions": [
                {"type": "open_url", "url": url},
                {"type": "wait_for_page_load", "timeout_sec": 20},
                {"type": "click_element_by_text", "text": click_text, "element_type": "any"},
            ],
            "thought": "Local shortcut: open URL and click text.",
        }

    # Pattern: multi-step local desktop instructions joined by "then"
    local_steps = _multi_step_local_actions(text)
    if local_steps:
        return {
            "answer": "Running your steps in order.",
            "actions": local_steps,
            "thought": "Local shortcut: parsed chained instructions.",
        }

    # Pattern: direct integration call in plain English
    execute_verb = any(v in lowered for v in ["call", "fetch", "run", "check", "pull", "query"])
    integration_hint = any(h in lowered for h in ["integration", "endpoint", "ai submit", "mihq", "sales and submit"])
    explicit_api_call_phrase = bool(re.search(r"\b(call|run|check|fetch|query)\b.*\b(api|integration|endpoint)\b", lowered))
    if not _is_howto_question(text) and (explicit_api_call_phrase or (execute_verb and integration_hint)):
        path_match = re.search(r"(/api/[\w\-\./?=&%]+)", text, re.IGNORECASE)
        path = path_match.group(1).strip() if path_match else ""

        method = "GET"
        if re.search(r"\bpost\b", lowered):
            method = "POST"
        elif re.search(r"\bput\b", lowered):
            method = "PUT"
        elif re.search(r"\bpatch\b", lowered):
            method = "PATCH"
        elif re.search(r"\bdelete\b", lowered):
            method = "DELETE"

        target_query = text
        m_target = re.search(r"(?:call|fetch|get|read|run|check)\s+(.+?)(?:\s+integration|\s+api|\s+endpoint|$)", text, re.IGNORECASE)
        if m_target:
            target_query = m_target.group(1).strip()

        integration = _find_integration_by_query(target_query)
        if integration is None and len(list_integrations()) == 1 and ("my integration" in lowered or "the integration" in lowered):
            only = list_integrations()[0]
            if isinstance(only, dict):
                integration = only
        if integration:
            integration_name = str(integration.get("name") or "").strip()
            if not path and ("ai submit" in integration_name.lower() or "mihq" in integration_name.lower()):
                path = "/api/external/ai-submits"
            action = {
                "type": "call_integration_api",
                "integration_name": integration_name,
                "method": method,
                "path": path,
            }
            return {
                "answer": f"Calling {integration_name} now.",
                "actions": [action],
                "thought": "Local shortcut: plain-English integration request.",
            }

    return None


def _build_system_prompt(learned_patterns: Optional[list] = None, conversation_summary: Optional[str] = None) -> str:
    """
    System instructions for the model. Keep it strict: return JSON only.
    Now includes learned patterns for adaptive decision-making and conversation memory!
    """
    base_prompt = (
        "You are Jarvis, a friendly and supportive personal assistant with advanced desktop automation capabilities.\n"
        "You have adaptive learning, persistent memory, and strategic multi-step reasoning abilities.\n\n"
        "PERSONALITY:\n"
        "- You are warm, encouraging, and genuinely helpful\n"
        "- You remember past conversations and build on that context\n"
        "- You anticipate user needs and offer proactive suggestions\n"
        "- You explain what you're doing in a clear, friendly way\n"
        "- You celebrate successes and provide encouragement when things don't go as planned\n\n"
        "CONVERSATIONAL STYLE:\n"
        "- Sound natural and human, not robotic or overly scripted\n"
        "- Use plain language with confident, helpful phrasing\n"
        "- Keep responses concise but personable, like top-tier chat assistants\n"
        "- When executing tasks, acknowledge intent and state what you are doing\n\n"
        "You will be given:\n"
        "- The user's instruction\n"
        "- Active window metadata\n"
        "- A screenshot (as an image)\n"
        "- Previous conversation context (if available)\n\n"
        "MULTI-STEP REASONING:\n"
        "- For complex tasks, break them down into logical steps\n"
        "- Consider dependencies between actions (e.g., wait for page load before clicking)\n"
        "- Think ahead: anticipate what state the system will be in after each action\n"
        "- Use the 'thought' field to document your reasoning process\n"
        "- Plan the entire sequence before executing\n"
        "- If a task requires >3 steps, use the 'actions' array instead of single 'action'\n\n"
        "Return ONLY valid JSON with this schema:\n"
        "{\n"
        '  "thought": string,\n'
        '  "answer": string,\n'
        '  "action": null | {\n'
        '    "type": "open_app_and_type" | "focus_app_and_type" | "save_active_file" | "open_url" | "open_url_and_click_result" | "fill_login_from_passwords" | "open_url_and_fill_login" | "browser_tab_next" | "browser_tab_prev" | "wait_for_page_load" | "search_page_for_identifier" | "close_current_tab" | "click_element_by_text" | "click_next_view_button" | "reset_view_button_counter" | "wait_for_element_with_text" | "call_integration_api" | "send_integration_webhook" | "check_ambetter_policy" | "check_priority_health_policy" | "export_ambetter_clients_csv" | "send_outlook_email" | "work_excel_file",\n'
        '    "app_name": string,\n'
        '    "text": string,\n'
        '    "filename": string,\n'
        '    "url": string,\n'
        '    "match_text": string,\n'
        '    "label": string,\n'
        '    "submit": boolean,\n'
        '    "identifier": string,\n'
        '    "search_type": string,\n'
        '    "timeout_sec": number,\n'
        '    "element_type": string,\n'
        '    "integration_name": string,\n'
        '    "method": string,\n'
        '    "path": string,\n'
        '    "query": object,\n'
        '    "payload": object,\n'
        '    "first_name": string,\n'
        '    "last_name": string,\n'
        '    "dob": string,\n'
        '    "member_id": string,\n'
        '    "policy_id": string,\n'
        '    "login_only": boolean,\n'
        '    "email_to": string,\n'
        '    "email_subject": string,\n'
        '    "email_body": string,\n'
        '    "instruction": string,\n'
        '    "file_path": string,\n'
        '    "sheet_name": string,\n'
        '    "output_filename": string\n'
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
        "- To wait for a page to load, use action.type=\"wait_for_page_load\" with optional timeout_sec.\n"
        "- To search for text/identifier on the current page, use action.type=\"search_page_for_identifier\" with identifier and search_type (\"text\", \"selector\", or \"xpath\").\n"
        "- To close the current browser tab, use action.type=\"close_current_tab\".\n"
        "- To click a button or link on the current page by its text, use action.type=\"click_element_by_text\" with text and optional element_type (\"button\", \"link\", or \"any\").\n"
        "- To click View buttons sequentially (for processing client lists), use action.type=\"click_next_view_button\" (no parameters needed - tracks automatically).\n"
        "- To reset the View button counter to start from the beginning, use action.type=\"reset_view_button_counter\".\n"
        "- To wait for specific text to appear on the page (like 'Sync Complete'), use action.type=\"wait_for_element_with_text\" with text and optional timeout_sec (default 30).\n"
        "- To call a saved API integration (ex: Keap), use action.type=\"call_integration_api\" with integration_name, optional method, optional path, and optional query/payload.\n"
        "- To send data to a saved webhook integration, use action.type=\"send_integration_webhook\" with integration_name and optional payload.\n"
        "- To check Ambetter policy details, use action.type=\"check_ambetter_policy\" with first_name, last_name, and optional dob/member_id/policy_id.\n"
        "- To only open/login Ambetter without checking a member, use action.type=\"check_ambetter_policy\" with login_only=true.\n"
        "- To check Priority Health policy details, use action.type=\"check_priority_health_policy\" with first_name, last_name, and optional dob/member_id/policy_id.\n"
        "- To export Ambetter clients to CSV, use action.type=\"export_ambetter_clients_csv\".\n"
        "- To send Outlook email, use action.type=\"send_outlook_email\" with email_to, email_subject, and email_body.\n"
        "- To work in an Excel/CSV file (sort/filter/remove duplicates and save a new copy), use action.type=\"work_excel_file\" with instruction and optional file_path/sheet_name/output_filename.\n"
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
    
    # Add learned patterns section if available
    if learned_patterns and len(learned_patterns) > 0:
        patterns_text = "\n\n🧠 ADAPTIVE LEARNING - Successful patterns I've learned:\n"
        for idx, pattern in enumerate(learned_patterns[:5], 1):  # Top 5 patterns
            pattern_type = pattern.get("pattern_type", "general")
            context = pattern.get("context", "unknown context")
            solution = pattern.get("solution", "unknown solution")
            success_count = pattern.get("success_count", 1)
            patterns_text += f"{idx}. [{pattern_type}] When '{context}', apply '{solution}' (✓{success_count} times)\n"
        
        patterns_text += (
            "\nIMPORTANT: The system automatically applies these learned patterns. "
            "Element interactions now have adaptive scrolling built-in. "
            "Trust that these intelligent behaviors are working behind the scenes.\n"
        )
        base_prompt += patterns_text
    
    # Add conversation memory context if available
    if conversation_summary:
        memory_text = f"\n\n💭 CONVERSATION MEMORY - Recent context:\n{conversation_summary}\n"
        memory_text += "\nIMPORTANT: Remember what the user has told you in previous conversations. "
        memory_text += "Refer to past context when relevant to provide continuity and personalized assistance.\n"
        base_prompt += memory_text
    
    return base_prompt


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


def _call_openai(user_text: str, window_info: dict, screenshot_png: Optional[bytes], memory_notes: Optional[list] = None, learned_patterns: Optional[list] = None, conversation_summary: Optional[str] = None) -> Dict[str, Any]:
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

    system_prompt = _build_system_prompt(learned_patterns=learned_patterns, conversation_summary=conversation_summary)
    memory_block = ""
    if memory_notes:
        memory_block = f"MEMORY_NOTES (recent):\n{json.dumps(memory_notes, ensure_ascii=False)}\n\n"

    password_summaries = list_password_entry_summaries()
    password_block = ""
    if password_summaries:
        password_block = f"PASSWORD_ENTRIES (label, url, username):\n{json.dumps(password_summaries, ensure_ascii=False)}\n\n"

    integration_summaries = []
    try:
        for entry in list_integrations():
            integration_summaries.append({
                "name": entry.get("name"),
                "kind": entry.get("kind"),
                "base_url": entry.get("base_url"),
                "webhook_url": entry.get("webhook_url"),
                "has_api_key": bool((entry.get("api_key") or "").strip()),
            })
    except Exception:
        integration_summaries = []

    integration_block = ""
    if integration_summaries:
        integration_block = f"INTEGRATIONS (saved):\n{json.dumps(integration_summaries, ensure_ascii=False)}\n\n"

    user_payload = (
        f"USER_INSTRUCTION:\n{user_text}\n\n"
        f"{memory_block}"
        f"{password_block}"
        f"{integration_block}"
        f"ACTIVE_WINDOW_INFO (JSON):\n{json.dumps(window_info, ensure_ascii=False)}\n"
    )

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    try:
        # Build messages for chat completion
        messages = [
            {"role": "system", "content": system_prompt},
        ]
        
        # Build user message with text and optional image
        user_content = []
        user_content.append({"type": "text", "text": user_payload})
        
        if screenshot_png:
            b64 = base64.b64encode(screenshot_png).decode("utf-8")
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}"
                }
            })
        
        messages.append({"role": "user", "content": user_content})
        
        resp = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.2,
            max_tokens=800,
        )

        text = (resp.choices[0].message.content or "").strip()
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
    if action_type not in {"open_app_and_type", "focus_app_and_type", "save_active_file", "open_url", "open_url_and_click_result", "fill_login_from_passwords", "open_url_and_fill_login", "browser_tab_next", "browser_tab_prev", "wait_for_page_load", "search_page_for_identifier", "close_current_tab", "click_element_by_text", "click_next_view_button", "reset_view_button_counter", "wait_for_element_with_text", "call_integration_api", "send_integration_webhook", "check_ambetter_policy", "check_priority_health_policy", "export_ambetter_clients_csv", "send_outlook_email", "work_excel_file"}:
        return {"executed": False, "result": None, "error": f"Unsupported action type: {action_type!r}"}

    app_name = str(action.get("app_name", "")).strip()
    text = str(action.get("text", "")).strip()
    filename = str(action.get("filename", "")).strip()
    url = str(action.get("url", "")).strip()
    match_text = str(action.get("match_text", "")).strip()
    label = str(action.get("label", "")).strip()
    integration_name = str(action.get("integration_name", "")).strip()
    first_name = str(action.get("first_name", "")).strip()
    last_name = str(action.get("last_name", "")).strip()
    dob = str(action.get("dob", "")).strip()
    member_id = str(action.get("member_id", "")).strip()
    policy_id = str(action.get("policy_id", "")).strip()
    login_only = bool(action.get("login_only", False))
    pause_after_export_click = bool(action.get("pause_after_export_click", False))
    email_to = str(action.get("email_to", "")).strip()
    email_subject = str(action.get("email_subject", "")).strip() or "Jarvis notification"
    email_body = str(action.get("email_body", "")).strip() or "Jarvis generated notification."
    excel_instruction = str(action.get("instruction", "")).strip() or text
    excel_file_path = str(action.get("file_path", "")).strip()
    excel_sheet_name = str(action.get("sheet_name", "")).strip()
    excel_output_filename = str(action.get("output_filename", "")).strip()
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
    if action_type in {"call_integration_api", "send_integration_webhook"} and not integration_name:
        return {"executed": False, "result": None, "error": "Missing action.integration_name"}
    if action_type == "check_ambetter_policy" and not login_only and not any([first_name and last_name, member_id, policy_id]):
        return {"executed": False, "result": None, "error": "Missing member identity. Provide first_name + last_name, member_id, or policy_id."}
    if action_type == "check_priority_health_policy" and not any([first_name and last_name, member_id, policy_id]):
        return {"executed": False, "result": None, "error": "Missing member identity. Provide first_name + last_name, member_id, or policy_id."}
    if action_type == "send_outlook_email" and not email_to:
        return {"executed": False, "result": None, "error": "Missing email_to for Outlook email tool."}
    if action_type == "work_excel_file" and not excel_instruction:
        return {"executed": False, "result": None, "error": "Missing instruction for Excel task."}

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
        if action_type == "wait_for_page_load":
            timeout_sec = float(action.get("timeout_sec", 30.0))
            ok = wait_for_page_load(timeout_sec=timeout_sec)
            if not ok:
                return {"executed": False, "result": None, "error": "Page load timed out or failed."}
            return {"executed": True, "result": {"type": action_type, "timeout_sec": timeout_sec}, "error": None}
        if action_type == "search_page_for_identifier":
            identifier = str(action.get("identifier", "")).strip()
            search_type = str(action.get("search_type", "text")).strip()
            if not identifier:
                return {"executed": False, "result": None, "error": "Missing identifier."}
            result = search_page_for_identifier(identifier, search_type=search_type)
            if result is None:
                return {"executed": False, "result": None, "error": "Search failed."}
            if not result.get("found"):
                return {"executed": False, "result": result, "error": f"Identifier '{identifier}' not found on page."}
            return {"executed": True, "result": result, "error": None}
        if action_type == "close_current_tab":
            ok = close_current_tab()
            if not ok:
                return {"executed": False, "result": None, "error": "Failed to close tab."}
            return {"executed": True, "result": {"type": action_type}, "error": None}
        if action_type == "click_element_by_text":
            element_text = str(action.get("text", "")).strip()
            element_type = str(action.get("element_type", "button")).strip()
            if not element_text:
                return {"executed": False, "result": None, "error": "Missing text for element to click."}
            ok = click_element_by_text(element_text, element_type=element_type)
            if not ok:
                return {"executed": False, "result": None, "error": f"Could not find or click element with text '{element_text}'."}
            return {"executed": True, "result": {"type": action_type, "text": element_text, "element_type": element_type}, "error": None}
        if action_type == "click_next_view_button":
            result = click_next_view_button()
            if not result.get("success"):
                return {"executed": False, "result": result, "error": "Failed to click next View button."}
            return {"executed": True, "result": result, "error": None}
        if action_type == "reset_view_button_counter":
            ok = reset_view_button_counter()
            return {"executed": True, "result": {"type": action_type}, "error": None}
        if action_type == "wait_for_element_with_text":
            element_text = str(action.get("text", "")).strip()
            timeout_sec = float(action.get("timeout_sec", 30.0))
            if not element_text:
                return {"executed": False, "result": None, "error": "Missing text to wait for."}
            ok = wait_for_element_with_text(element_text, timeout_sec=timeout_sec)
            if not ok:
                return {"executed": False, "result": None, "error": f"Text '{element_text}' did not appear within {timeout_sec} seconds."}
            return {"executed": True, "result": {"type": action_type, "text": element_text, "timeout_sec": timeout_sec}, "error": None}
        if action_type == "send_outlook_email":
            recipients = [item.strip() for item in email_to.split(",") if item.strip()]
            ok, msg = send_assistance_email(email_subject, email_body, recipients)
            if not ok:
                return {
                    "executed": False,
                    "result": {
                        "type": action_type,
                        "email_to": recipients,
                        "email_subject": email_subject,
                    },
                    "error": msg,
                }
            return {
                "executed": True,
                "result": {
                    "type": action_type,
                    "email_to": recipients,
                    "email_subject": email_subject,
                    "status": msg,
                },
                "error": None,
            }
        if action_type == "check_ambetter_policy":
            if AmbetterWorker is None:
                return {
                    "executed": False,
                    "result": {"type": action_type, "carrier": "ambetter", "success": False},
                    "error": "Ambetter worker unavailable.",
                }
            member_data = {
                "first_name": first_name,
                "last_name": last_name,
                "dob": dob,
                "member_id": member_id,
                "policy_id": policy_id,
            }
            worker = AmbetterWorker()
            if login_only:
                response_data = worker.run_login_only()
            else:
                response_data = worker.run(member_data)
            if not isinstance(response_data, dict):
                response_data = {
                    "carrier": "ambetter",
                    "success": False,
                    "error": "Ambetter worker returned invalid response.",
                }
            ok = bool(response_data.get("success"))
            if not ok:
                return {
                    "executed": False,
                    "result": {
                        "type": action_type,
                        "carrier": "ambetter",
                        "member": member_data,
                        "login_only": login_only,
                        "response": response_data,
                    },
                    "error": str(response_data.get("error") or "Ambetter policy check failed."),
                }
            return {
                "executed": True,
                "result": {
                    "type": action_type,
                    "carrier": "ambetter",
                    "member": member_data,
                    "login_only": login_only,
                    "response": response_data,
                },
                "error": None,
            }
        if action_type == "check_priority_health_policy":
            if PriorityHealthWorker is None:
                return {
                    "executed": False,
                    "result": {"type": action_type, "carrier": "priority_health", "success": False},
                    "error": "Priority Health worker unavailable.",
                }
            member_data = {
                "first_name": first_name,
                "last_name": last_name,
                "dob": dob,
                "member_id": member_id,
                "policy_id": policy_id,
            }
            worker = PriorityHealthWorker()
            response_data = worker.run(member_data)
            if not isinstance(response_data, dict):
                response_data = {
                    "carrier": "priority_health",
                    "success": False,
                    "error": "Priority Health worker returned invalid response.",
                }
            ok = bool(response_data.get("success"))
            if not ok:
                return {
                    "executed": False,
                    "result": {
                        "type": action_type,
                        "carrier": "priority_health",
                        "member": member_data,
                        "response": response_data,
                    },
                    "error": str(response_data.get("error") or "Priority Health policy check failed."),
                }
            return {
                "executed": True,
                "result": {
                    "type": action_type,
                    "carrier": "priority_health",
                    "member": member_data,
                    "response": response_data,
                },
                "error": None,
            }
        if action_type == "export_ambetter_clients_csv":
            if AmbetterWorker is None:
                return {
                    "executed": False,
                    "result": {"type": action_type, "carrier": "ambetter", "success": False},
                    "error": "Ambetter worker unavailable.",
                }
            worker = AmbetterWorker()
            response_data = worker.run_export_clients_csv(pause_after_export_click=pause_after_export_click)
            if not isinstance(response_data, dict):
                response_data = {
                    "carrier": "ambetter",
                    "success": False,
                    "error": "Ambetter worker returned invalid response.",
                }
            ok = bool(response_data.get("success"))
            if not ok:
                return {
                    "executed": False,
                    "result": {
                        "type": action_type,
                        "carrier": "ambetter",
                        "response": response_data,
                    },
                    "error": str(response_data.get("error") or "Ambetter CSV export failed."),
                }
            return {
                "executed": True,
                "result": {
                    "type": action_type,
                    "carrier": "ambetter",
                    "response": response_data,
                },
                "error": None,
            }
        if action_type == "send_integration_webhook":
            payload = action.get("payload")
            if isinstance(payload, str):
                payload = _safe_json_loads(payload) if payload.strip() else None
            if payload is not None and not isinstance(payload, dict):
                return {"executed": False, "result": None, "error": "Webhook payload must be a JSON object."}
            ok, msg, response_data = send_webhook(integration_name, payload=payload)
            if not ok:
                return {"executed": False, "result": {"type": action_type, "integration_name": integration_name, "response": response_data}, "error": msg}
            return {"executed": True, "result": {"type": action_type, "integration_name": integration_name, "status": msg, "response": response_data}, "error": None}
        if action_type == "work_excel_file":
            response_data = run_excel_sheet_task(
                instruction=excel_instruction,
                file_path=excel_file_path,
                sheet_name=excel_sheet_name,
                output_filename=excel_output_filename,
            )
            if not isinstance(response_data, dict):
                response_data = {
                    "success": False,
                    "error": "Excel worker returned invalid response.",
                }
            ok = bool(response_data.get("success"))
            if not ok:
                return {
                    "executed": False,
                    "result": {
                        "type": action_type,
                        "instruction": excel_instruction,
                        "file_path": excel_file_path,
                        "response": response_data,
                    },
                    "error": str(response_data.get("error") or "Excel task failed."),
                }
            return {
                "executed": True,
                "result": {
                    "type": action_type,
                    "instruction": excel_instruction,
                    "file_path": excel_file_path,
                    "sheet_name": excel_sheet_name,
                    "response": response_data,
                },
                "error": None,
            }
        if action_type == "call_integration_api":
            method = str(action.get("method", "GET") or "GET").upper()
            path = str(action.get("path", "") or "").strip()
            query = action.get("query")
            payload = action.get("payload")
            if isinstance(query, str):
                query = _safe_json_loads(query) if query.strip() else None
            if isinstance(payload, str):
                payload = _safe_json_loads(payload) if payload.strip() else None
            if query is not None and not isinstance(query, dict):
                return {"executed": False, "result": None, "error": "API query must be a JSON object."}
            if payload is not None and not isinstance(payload, dict):
                return {"executed": False, "result": None, "error": "API payload must be a JSON object."}

            if "airtable" in integration_name.lower():
                default_table_id = os.getenv("AIRTABLE_DEFAULT_TABLE_ID", "tblaSejx38hois2uu").strip() or "tblaSejx38hois2uu"
                lowered_path = path.lower()
                if "/clients" in lowered_path or lowered_path.endswith("clients"):
                    suffix = ""
                    if "?" in path:
                        suffix = path[path.find("?"):]
                    path = f"{default_table_id}{suffix}"
                elif not path or path == "/":
                    path = f"{default_table_id}?maxRecords=5"

            ok, msg, response_data = call_api(
                integration_name,
                method=method,
                path=path,
                query=query,
                payload=payload,
            )
            if not ok:
                return {"executed": False, "result": {"type": action_type, "integration_name": integration_name, "response": response_data}, "error": msg}
            return {"executed": True, "result": {"type": action_type, "integration_name": integration_name, "method": method, "path": path, "status": msg, "response": response_data}, "error": None}
    except Exception as e:
        return {"executed": False, "result": None, "error": f"Action failed: {type(e).__name__}: {e}"}


def _summarize_execution_for_user(exec_results: list) -> str:
    if not exec_results:
        return ""
    airtable_searched_names = []
    airtable_found_names = []
    airtable_records = []

    for entry in exec_results:
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        if str(result.get("type") or "") != "call_integration_api":
            continue
        integration_name = str(result.get("integration_name") or "").strip().lower()
        if "airtable" not in integration_name:
            continue

        path = str(result.get("path") or "")
        m = re.search(r"\{Name\}\s*=\s*'([^']+)'", path)
        if m:
            airtable_searched_names.append(m.group(1).strip())

        response = result.get("response")
        if isinstance(response, dict):
            records = response.get("records")
            if isinstance(records, list):
                airtable_records.extend([r for r in records if isinstance(r, dict)])
                for rec in records:
                    if not isinstance(rec, dict):
                        continue
                    fields = rec.get("fields") if isinstance(rec.get("fields"), dict) else {}
                    nm = str(fields.get("Name") or "").strip()
                    if nm:
                        airtable_found_names.append(nm)

    if airtable_records:
        _LAST_AIRTABLE_LOOKUP["searched_names"] = airtable_searched_names
        _LAST_AIRTABLE_LOOKUP["records"] = airtable_records
        _LAST_AIRTABLE_LOOKUP["pending_name"] = ""
        _LAST_AIRTABLE_LOOKUP["pending_options"] = []
        _LAST_AIRTABLE_LOOKUP["pending_detail"] = {}

    if airtable_searched_names:
        searched_unique = []
        seen_search = set()
        for name in airtable_searched_names:
            key = _normalize_person_name(name)
            if key in seen_search:
                continue
            seen_search.add(key)
            searched_unique.append(name)

        found_unique = []
        seen_found = set()
        for name in airtable_found_names:
            key = _normalize_person_name(name)
            if key in seen_found:
                continue
            seen_found.add(key)
            found_unique.append(name)

        missing = [name for name in searched_unique if _normalize_person_name(name) not in seen_found]
        found_counts: Dict[str, int] = {}
        display_names: Dict[str, str] = {}
        for name in airtable_found_names:
            key = _normalize_person_name(name)
            found_counts[key] = found_counts.get(key, 0) + 1
            display_names[key] = name
        duplicate_notes = [f"{display_names[k]} ({count} records)" for k, count in found_counts.items() if count > 1]

        if found_unique or missing:
            parts = []
            if found_unique:
                parts.append(f"Found: {', '.join(found_unique)}")
            if missing:
                parts.append(f"Not found: {', '.join(missing)}")
            if duplicate_notes:
                parts.append(f"Duplicates: {', '.join(duplicate_notes)}")
            joined = ". ".join(parts)
            return f"{joined}. Tell me what specific info you want (phone, DOB, appointment date, effective date, or notes)."

    for entry in reversed(exec_results):
        if not isinstance(entry, dict):
            continue
        entry_error = str(entry.get("error") or "").strip()
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        rtype = result.get("type")
        if rtype not in {"call_integration_api", "send_integration_webhook", "check_ambetter_policy", "check_priority_health_policy", "export_ambetter_clients_csv", "send_outlook_email", "work_excel_file"}:
            continue
        integration_name = str(result.get("integration_name") or "this integration").strip()
        if entry_error:
            short_error = entry_error if len(entry_error) <= 260 else (entry_error[:260] + "...")
            if rtype == "check_ambetter_policy":
                return f"I couldn't complete the Ambetter policy check: {short_error}"
            if rtype == "check_priority_health_policy":
                return f"I couldn't complete the Priority Health policy check: {short_error}"
            if rtype == "export_ambetter_clients_csv":
                return f"I couldn't export the Ambetter clients CSV: {short_error}"
            if rtype == "send_outlook_email":
                return f"I couldn't send the Outlook email: {short_error}"
            if rtype == "work_excel_file":
                return f"I couldn't complete the Excel task: {short_error}"
            return f"I couldn't complete the {integration_name} request: {short_error}"

        if rtype == "check_ambetter_policy":
            response = result.get("response") if isinstance(result.get("response"), dict) else {}
            if bool(result.get("login_only")) or bool(response.get("portal_ready")):
                return "Ambetter portal is open and you are signed in."
            member_name = str(response.get("member_name") or "the member").strip()
            policy_status = str(response.get("policy_status") or "").strip()
            paid_through_date = str(response.get("paid_through_date") or "").strip()
            policy_number = str(response.get("policy_number") or "").strip()
            parts = []
            if policy_status:
                parts.append(f"status: {policy_status}")
            if paid_through_date:
                parts.append(f"paid through: {paid_through_date}")
            if policy_number:
                parts.append(f"policy #: {policy_number}")
            if not parts:
                return f"Ambetter check completed for {member_name}."
            return f"Ambetter result for {member_name}: " + ", ".join(parts)
        if rtype == "check_priority_health_policy":
            response = result.get("response") if isinstance(result.get("response"), dict) else {}
            member_name = str(response.get("member_name") or "the member").strip()
            policy_status = str(response.get("policy_status") or "").strip()
            paid_through_date = str(response.get("paid_through_date") or "").strip()
            policy_number = str(response.get("policy_number") or "").strip()
            parts = []
            if policy_status:
                parts.append(f"status: {policy_status}")
            if paid_through_date:
                parts.append(f"paid through: {paid_through_date}")
            if policy_number:
                parts.append(f"policy #: {policy_number}")
            if not parts:
                return f"Priority Health check completed for {member_name}."
            return f"Priority Health result for {member_name}: " + ", ".join(parts)
        if rtype == "export_ambetter_clients_csv":
            response = result.get("response") if isinstance(result.get("response"), dict) else {}
            if bool(response.get("paused_after_export_click")):
                pause_seconds = int(response.get("pause_seconds") or 0)
                return f"Clicked Ambetter export and paused for {pause_seconds} seconds. Send me the blue Download button selector from the popup."
            file_path = str(response.get("file_path") or "").strip()
            if file_path:
                return f"Ambetter clients CSV exported successfully to: {file_path}"
            return "Ambetter clients CSV exported successfully."
        if rtype == "send_outlook_email":
            recipients = result.get("email_to") if isinstance(result.get("email_to"), list) else []
            to_line = ", ".join(str(x) for x in recipients if str(x).strip())
            subject = str(result.get("email_subject") or "").strip()
            if to_line and subject:
                return f"Outlook email sent to {to_line} with subject '{subject}'."
            if to_line:
                return f"Outlook email sent to {to_line}."
            return "Outlook email sent."
        if rtype == "work_excel_file":
            response = result.get("response") if isinstance(result.get("response"), dict) else {}
            output_file = str(response.get("file_path") or "").strip()
            rows_before = response.get("rows_before")
            rows_after = response.get("rows_after")
            notes = response.get("notes") if isinstance(response.get("notes"), list) else []
            details = []
            if isinstance(rows_before, int) and isinstance(rows_after, int):
                details.append(f"rows: {rows_before} → {rows_after}")
            if notes:
                details.append("; ".join(str(n) for n in notes[:2]))
            if output_file:
                suffix = f" ({', '.join(details)})" if details else ""
                return f"Excel task completed and saved to: {output_file}{suffix}"
            return "Excel task completed and saved a new copy."
        response = result.get("response")
        if response is None:
            continue

        if isinstance(response, dict):
            raw_payload = str(response.get("raw") or "").strip().lower()
            if raw_payload.startswith("<!doctype html") or raw_payload.startswith("<html"):
                return (
                    "I reached a website page instead of API data. "
                    "Try path '/api/external/ai-submits' for the MIHQ AI Submits integration."
                )

            leads = response.get("leads")
            total = response.get("total")
            if isinstance(leads, list):
                count = len(leads)
                names = []
                for item in leads[:3]:
                    if isinstance(item, dict):
                        nm = str(item.get("name") or "").strip()
                        if nm:
                            names.append(nm)
                names_part = f" Top names: {', '.join(names)}." if names else ""
                total_part = f" (total: {total})" if total is not None else ""
                return f"Integration response: {count} lead(s) returned{total_part}.{names_part}"

        response_text = json.dumps(response, ensure_ascii=False) if response else ""
        if len(response_text) > 600:
            response_text = response_text[:600] + "..."
        if rtype == "call_integration_api":
            return f"Integration response: {response_text}"
        return f"Webhook response: {response_text}"
    return ""


def _execute_with_recovery(action: Optional[dict], user_text: str = "", window_info: dict = None, max_retries: int = 2) -> Dict[str, Any]:
    """
    Execute an action with automatic failure learning and recovery.
    
    Args:
        action: Action to execute
        user_text: Original user instruction (for context)
        window_info: Window context (for learning)
        max_retries: Maximum recovery attempts
    
    Returns:
        Execution result with recovery info
    """
    if not action:
        return {"executed": False, "result": None, "error": None}
    
    failure_system = get_failure_system()
    
    # First attempt
    result = _maybe_execute_action(action)
    
    if result.get("executed") and not result.get("error"):
        # Success on first try
        return result
    
    # Action failed - record the failure
    error_msg = result.get("error", "Unknown error")
    context = {
        "user_input": user_text,
        "window": window_info.get("title") if window_info else None,
        "window_process": window_info.get("process_name") if window_info else None
    }
    
    failure_id = failure_system.record_failure(action, error_msg, context)
    
    # Check for automatic recovery strategy
    recovery_action = failure_system.suggest_recovery(action, error_msg)
    
    if not recovery_action:
        # No known recovery strategy
        result["failure_id"] = failure_id
        result["recovery_attempted"] = False
        return result
    
    # Attempt recovery
    for retry_num in range(max_retries):
        time.sleep(0.5)  # Brief delay before retry
        
        recovery_result = _maybe_execute_action(recovery_action)
        
        if recovery_result.get("executed") and not recovery_result.get("error"):
            # Recovery successful!
            failure_system.record_recovery_attempt(failure_id, recovery_action, success=True)
            return {
                "executed": True,
                "result": recovery_result.get("result"),
                "error": None,
                "recovered": True,
                "original_error": error_msg,
                "recovery_strategy": recovery_action.get("type")
            }
        
        # Recovery failed, record it
        failure_system.record_recovery_attempt(failure_id, recovery_action, success=False)
    
    # All recovery attempts failed
    result["failure_id"] = failure_id
    result["recovery_attempted"] = True
    result["recovery_failed"] = True
    return result


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

    # Greeting/small-talk detection

    GREETING_KEYWORDS = [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening", "greetings", "how are you", "what's up", "how's it going", "my name is", "nice to meet you", "good day"
    ]
    WEATHER_KEYWORDS = [
        "weather", "forecast", "temperature", "rain", "sunny", "cloudy", "windy", "is it raining", "is it sunny", "is it cloudy"
    ]
    user_text_lower = (user_text or "").strip().lower()

    detail_answer = _maybe_answer_airtable_detail_request(user_text)
    if detail_answer:
        response = {
            "ok": True,
            "timestamp": start,
            "elapsed_sec": 0.0,
            "input": user_text,
            "active_window": {},
            "screenshot_bytes_len": 0,
            "model": {
                "used": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "raw_text": "",
                "parsed_json": None,
                "thought": "Answered from last Airtable lookup cache.",
                "answer": detail_answer,
                "action": None,
                "actions": None,
                "error": None,
            },
            "execution": {"executed": False, "result": None, "error": None},
        }
        try:
            conv_memory = get_conversation_memory()
            conv_memory.add_message("user", user_text)
            conv_memory.add_message("assistant", detail_answer)
        except Exception:
            pass
        return response

    # Weather query detection
    if any(kw in user_text_lower for kw in WEATHER_KEYWORDS):
        location = _extract_weather_location(user_text)
        weather_info = _fetch_weather_summary(location)
        answer = weather_info or f"I couldn't fetch live weather for {location} right now. If you want, I can still help with your next task."
        response = {
            "ok": True,
            "timestamp": start,
            "elapsed_sec": 0.0,
            "input": user_text,
            "active_window": {},
            "screenshot_bytes_len": 0,
            "model": {
                "used": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "raw_text": "",
                "parsed_json": None,
                "thought": "Answered weather query using local weather fetch.",
                "answer": answer,
                "action": None,
                "actions": None,
                "error": None,
            },
            "execution": {"executed": False, "result": None, "error": None},
        }
        # Save to conversation memory for continuity
        try:
            conv_memory = get_conversation_memory()
            conv_memory.add_message("user", user_text)
            conv_memory.add_message("assistant", response["model"]["answer"])
        except Exception:
            pass
        return response

    # PyAutoGUI safety: prevent runaway by moving mouse to top-left corner
    pyautogui.FAILSAFE = True

    window_info = {}
    screenshot_png = None

    # Gather context (never hard-crash)
    try:
        window_info = get_active_window_info()
    except Exception as e:
        # Local fallback for simple desktop actions
        fallback_action = _local_fallback_action(user_text)
        if fallback_action:
            answer = f"Okay, opening {fallback_action.get('app_name')}." if fallback_action.get('app_name') else "OK."
            response = {
                "ok": True,
                "timestamp": start,
                "elapsed_sec": 0.0,
                "input": user_text,
                "active_window": {},
                "screenshot_bytes_len": 0,
                "model": {
                    "used": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    "raw_text": "",
                    "parsed_json": None,
                    "thought": "Local desktop action fallback.",
                    "answer": answer,
                    "action": fallback_action,
                    "actions": None,
                    "error": None,
                },
                "execution": {"executed": False, "result": None, "error": None},
            }
            try:
                conv_memory = get_conversation_memory()
                conv_memory.add_message("user", user_text)
                conv_memory.add_message("assistant", answer)
            except Exception:
                pass
            return response
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
            exec_result = _execute_with_recovery(action, user_text, window_info) if execute_actions else {"executed": False, "result": None, "error": None}
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

    local_shortcut = _local_instruction_shortcut(user_text)
    if isinstance(local_shortcut, dict) and isinstance(local_shortcut.get("actions"), list):
        planned_actions = [a for a in local_shortcut.get("actions") if isinstance(a, dict)]
        normalized_actions = []
        for item in planned_actions:
            prepared = _coerce_web_focus_action(item, user_text, window_info)
            prepared = _maybe_upgrade_to_login_action(prepared)
            normalized_actions.append(prepared)

        exec_results = []
        execution = {"executed": False, "result": None, "error": None}
        if execute_actions and normalized_actions:
            for next_action in normalized_actions[:max_steps]:
                step_result = _execute_with_recovery(next_action, user_text, window_info)
                exec_results.append(step_result)
                if step_result.get("error"):
                    break

            any_executed = any(r.get("executed") for r in exec_results if isinstance(r, dict))
            first_error = next((r.get("error") for r in exec_results if isinstance(r, dict) and r.get("error")), None)
            execution = {
                "executed": any_executed,
                "result": exec_results if exec_results else None,
                "error": first_error,
            }

        answer = str(local_shortcut.get("answer") or "OK.")
        execution_summary = _summarize_execution_for_user(exec_results)
        if execution_summary and execution_summary not in answer:
            answer = f"{answer}\n{execution_summary}"
        answer = _humanize_assistant_answer(user_text, answer, local_shortcut.get("actions"))

        try:
            conv_memory.add_message("user", user_text)
            conv_memory.add_message("assistant", answer)
        except Exception:
            pass

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
                "thought": local_shortcut.get("thought"),
                "answer": answer,
                "action": None,
                "actions": local_shortcut.get("actions"),
                "error": None,
            },
            "execution": execution,
        }
    # Fallback: for any other question, always call OpenAI and return its answer
    # This ensures Jarvis can answer anything (weather, current events, general queries)
    memory_notes = get_memory_notes(limit=5)
    learned_patterns = get_learning_patterns(min_success=1)
    conv_memory = get_conversation_memory()
    conversation_summary = conv_memory.get_recent_summary(num_messages=10)
    model_result = _call_openai(
        user_text=instruction,
        window_info=window_info,
        screenshot_png=screenshot_png,
        memory_notes=memory_notes,
        learned_patterns=learned_patterns,
        conversation_summary=conversation_summary if conversation_summary != "No conversation history." else None,
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

    planned_actions = []
    if isinstance(actions, list) and actions:
        planned_actions = [a for a in actions if isinstance(a, dict)]
    elif isinstance(action, dict):
        planned_actions = [action]

    if planned_actions:
        normalized_actions = []
        for item in planned_actions:
            prepared = _coerce_web_focus_action(item, user_text, window_info)
            prepared = _maybe_upgrade_to_login_action(prepared)
            normalized_actions.append(prepared)
        planned_actions = normalized_actions

    execution = {"executed": False, "result": None, "error": None}
    if execute_actions and planned_actions:
        for next_action in planned_actions[:max_steps]:
            step_result = _execute_with_recovery(next_action, user_text, window_info)
            exec_results.append(step_result)
            if step_result.get("error"):
                break

        any_executed = any(r.get("executed") for r in exec_results if isinstance(r, dict))
        first_error = next((r.get("error") for r in exec_results if isinstance(r, dict) and r.get("error")), None)
        execution = {
            "executed": any_executed,
            "result": exec_results if exec_results else None,
            "error": first_error,
        }

        execution_summary = _summarize_execution_for_user(exec_results)
        if execution_summary:
            if not answer:
                answer = execution_summary
            elif execution_summary not in answer:
                answer = f"{answer}\n{execution_summary}"
    if not answer and (action or actions):
        answer = "OK."
    answer = _humanize_assistant_answer(user_text, answer, planned_actions)
    try:
        conv_memory.add_message("user", user_text)
        if answer:
            conv_memory.add_message("assistant", answer)
    except Exception:
        pass
    return {
        "ok": bool(model_result.get("ok")),
        "timestamp": start,
        "elapsed_sec": round(_now_ts() - start, 3),
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
        "execution": execution,
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
