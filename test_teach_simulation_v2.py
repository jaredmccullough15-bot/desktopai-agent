import json
import sys
from datetime import datetime, timezone

import requests

BASE = "http://127.0.0.1:8010"

passes = []
fails = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        passes.append(name)
        print(f"[PASS] {name}")
    else:
        fails.append(name)
        print(f"[FAIL] {name}: {detail}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def post(path: str, payload: dict):
    return requests.post(f"{BASE}{path}", json=payload, timeout=20)


def get(path: str):
    return requests.get(f"{BASE}{path}", timeout=20)


print("=== 1) Health ===")
r = get("/health")
check("health_200", r.status_code == 200, str(r.status_code))

print("\n=== 2) Create draft ===")
r = post(
    "/api/brain/workflow-learning/drafts",
    {
        "workflow_name": "TrackVia Local Predeploy Test",
        "learning_path": "demonstration",
        "goal": "Validate teaching session capture pipeline",
        "source_text": "",
    },
)
check("draft_create_200", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:240]}")
if r.status_code not in (200, 201):
    print("Stopping due to draft creation failure")
    sys.exit(1)

draft = r.json()
draft_id = draft.get("draft_id") or draft.get("id")
check("draft_id_present", bool(draft_id), json.dumps(draft)[:240])

print("\n=== 3) Start teach session (local subprocess path) ===")
r = post(
    f"/api/brain/workflow-learning/drafts/{draft_id}/teach-session/start",
    {
        "start_url": "https://go.trackvia.com/#/signin",
        "api_base": BASE,
        "target_machine_uuid": "",
    },
)
check("teach_start_200", r.status_code in (200, 201), f"status={r.status_code} body={r.text[:300]}")
if r.status_code not in (200, 201):
    print("Stopping due to teach-session start failure")
    sys.exit(1)

start_body = r.json()
session_id = start_body.get("session_id")
check("session_id_returned", bool(session_id), json.dumps(start_body)[:300])

print("\n=== 4) Post status active ===")
r = post(
    f"/api/teaching/session/{session_id}/status",
    {
        "status": "active",
        "task_id": start_body.get("task_id") or "local-test-task",
        "message": "Teaching browser opened successfully. Walk me through the workflow.",
    },
)
check("status_active_200", r.status_code == 200, f"status={r.status_code} body={r.text[:240]}")

print("\n=== 5) Post context snapshot ===")
context_payload = {
    "url": "https://go.trackvia.com/#/signin",
    "title": "TrackVia - Sign In",
    "visible_buttons": [
        {"label": "Sign In", "selector": "button[type='submit']"},
        {"label": "Forgot Password", "selector": "a.forgot-link"},
    ],
    "visible_inputs": [
        {"label": "Email", "selector": "input[type='email']", "value_redacted": "[redacted]"},
        {"label": "Password", "selector": "input[type='password']", "value_redacted": "[redacted]"},
    ],
    "visible_links": [
        {"label": "Forgot Password", "href": "https://go.trackvia.com/reset"}
    ],
}
r = post(f"/api/teaching/session/{session_id}/context", context_payload)
check("context_post_200", r.status_code == 200, f"status={r.status_code} body={r.text[:240]}")

print("\n=== 6) Post click action ===")
action_payload = {
    "action": {
        "id": "evt-1",
        "type": "click",
        "selector": "button[type='submit']",
        "label": "Sign In",
        "value_redacted": None,
        "url": "https://go.trackvia.com/#/signin",
        "timestamp": now_iso(),
    },
    "step_id": None,
    "page_context": None,
}
r = post(f"/api/teaching/session/{session_id}/actions", action_payload)
check("action_post_200", r.status_code == 200, f"status={r.status_code} body={r.text[:300]}")

print("\n=== 7) Debug endpoint assertions ===")
r = get(f"/api/teaching/session/{session_id}/debug")
check("debug_200", r.status_code == 200, f"status={r.status_code} body={r.text[:240]}")
if r.status_code == 200:
    dbg = r.json()
    check("has_page_context_snapshot", bool(dbg.get("has_page_context_snapshot")), str(dbg.get("has_page_context_snapshot")))
    check("observed_actions_count_gt0", int(dbg.get("observed_actions_count") or 0) > 0, str(dbg.get("observed_actions_count")))
    check("page_context_url_is_trackvia", "trackvia" in str(dbg.get("page_context_url") or "").lower(), str(dbg.get("page_context_url")))
    check("button_count_gt0", int(dbg.get("page_context_button_count") or 0) > 0, str(dbg.get("page_context_button_count")))
    check("input_count_gt0", int(dbg.get("page_context_input_count") or 0) > 0, str(dbg.get("page_context_input_count")))

print("\n=== 8) Status poll assertions ===")
r = get(f"/api/teaching/session/{session_id}/status")
check("status_get_200", r.status_code == 200, f"status={r.status_code} body={r.text[:240]}")
if r.status_code == 200:
    st = r.json()
    raw = json.dumps(st).lower()
    print(json.dumps(st, indent=2)[:1200])
    ts = st.get("teaching_session") or {}
    check("status_contains_context", "page_context_snapshot" in ts, "missing teaching_session.page_context_snapshot")
    check("no_plaintext_password", "password" not in raw or "[redacted]" in raw, "password marker detected")

print("\n=== Summary ===")
print(f"PASS={len(passes)} FAIL={len(fails)}")
if fails:
    print("Failed checks:", ", ".join(fails))
    sys.exit(1)
print("All simulation checks passed.")
