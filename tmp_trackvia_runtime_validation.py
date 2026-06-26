import json
import time
import uuid
from typing import Any

import requests

BASE_URL = "http://bill-core-env.eba-e7menpcq.us-east-2.elasticbeanstalk.com"
MACHINE_UUID = "201b5282-3724-4115-b02b-721a7a0b9a2d"
TRACKVIA_URL = "https://go.trackvia.com/?_gl=1*cf973j*_ga*MTk5Mzg5NDAwMy4xNjc5MDU3NjQ5*_ga_XMMWW2S2NC*MTY3OTA1NzY0OC4xLjAuMTY3OTA1NzY0OC4wLjAuMA..#/signin"


def req(method: str, path: str, **kwargs: Any) -> requests.Response:
    url = f"{BASE_URL}{path}"
    resp = requests.request(method, url, timeout=30, **kwargs)
    return resp


def wait_for_status(session_id: str, target: str, timeout_s: int = 180) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        r = req("GET", f"/api/teaching/session/{session_id}/status")
        if r.status_code == 200:
            last = r.json()
            if str(last.get("status") or "") == target:
                return last
        time.sleep(2)
    return last


def wait_for_snapshot(session_id: str, timeout_s: int = 180) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    best: dict[str, Any] = {}
    while time.time() < deadline:
        r = req("GET", f"/api/teaching/session/{session_id}/status")
        if r.status_code == 200:
            data = r.json()
            ts = data.get("teaching_session") or {}
            snap = ts.get("page_context_snapshot") or {}
            best = snap
            domain = str(snap.get("domain") or "").lower()
            url = str(snap.get("url") or "").lower()
            inputs = snap.get("visible_inputs") or snap.get("inputs") or []
            buttons = snap.get("visible_buttons") or snap.get("buttons") or []
            inputs_text = json.dumps(inputs).lower()
            buttons_text = json.dumps(buttons).lower()
            looks_good = (
                ("go.trackvia.com" in domain)
                and (("#/signin" in url) or ("signin" in url) or ("sign-in" in url))
                and ("email" in inputs_text)
                and ("password" in inputs_text)
                and ("sign in" in buttons_text)
            )
            if looks_good:
                return snap
        time.sleep(2)
    return best


def main() -> None:
    run_id = uuid.uuid4().hex[:8]
    workflow_name = f"TrackVia Teach Validation {run_id}"
    out: dict[str, Any] = {
        "workflow_name": workflow_name,
        "machine_uuid": MACHINE_UUID,
    }

    create_payload = {
        "learning_path": "demonstration",
        "workflow_name": workflow_name,
        "goal": "Validate teaching-mode capture runtime for TrackVia login flow",
        "source_text": "",
    }
    r_create = req("POST", "/api/brain/workflow-learning/drafts", json=create_payload)
    out["create_status"] = r_create.status_code
    if r_create.status_code != 200:
        out["error"] = "create_draft_failed"
        out["create_body"] = r_create.text
        print(json.dumps(out, indent=2))
        return
    draft = r_create.json()
    draft_id = str(draft.get("draft_id") or "")
    out["draft_id"] = draft_id

    start_payload = {
        "target_machine_uuid": MACHINE_UUID,
        "api_base": BASE_URL,
        "start_url": TRACKVIA_URL,
    }
    r_start = req("POST", f"/api/brain/workflow-learning/drafts/{draft_id}/teach-session/start", json=start_payload)
    out["start_status"] = r_start.status_code
    out["start_body"] = r_start.json() if r_start.status_code == 200 else r_start.text
    if r_start.status_code != 200:
        out["error"] = "start_teach_failed"
        print(json.dumps(out, indent=2))
        return

    session_id = str((r_start.json() or {}).get("session_id") or "")
    task_id = str((r_start.json() or {}).get("task_id") or "")
    out["session_id"] = session_id
    out["task_id"] = task_id

    status_active = wait_for_status(session_id, "active", timeout_s=180)
    out["status_after_wait"] = status_active.get("status")

    r_msg1 = req("POST", f"/api/teaching/session/{session_id}/conversation", json={"message": "log into TrackVia"})
    out["msg1_status"] = r_msg1.status_code
    out["msg1_reply"] = (r_msg1.json() or {}).get("reply") if r_msg1.status_code == 200 else r_msg1.text

    nav_message = f"navigate to the TrackVia login page at {TRACKVIA_URL}"
    r_msg2 = req("POST", f"/api/teaching/session/{session_id}/conversation", json={"message": nav_message})
    out["msg2_status"] = r_msg2.status_code
    out["msg2_reply"] = (r_msg2.json() or {}).get("reply") if r_msg2.status_code == 200 else r_msg2.text

    step_id = ""
    step_title = ""
    if r_msg2.status_code == 200:
        ts = (r_msg2.json() or {}).get("teaching_session") or {}
        steps = ts.get("steps") or []
        if steps:
            last = steps[-1]
            step_id = str(last.get("id") or "")
            step_title = str(last.get("title") or "")
    out["navigation_step_id"] = step_id
    out["navigation_step_title"] = step_title

    if step_id:
        r_confirm_nav = req("POST", f"/api/teaching/session/{session_id}/steps/{step_id}/confirm")
        out["confirm_nav_status"] = r_confirm_nav.status_code
        out["confirm_nav_reply"] = (r_confirm_nav.json() or {}).get("reply") if r_confirm_nav.status_code == 200 else r_confirm_nav.text

    snapshot = wait_for_snapshot(session_id, timeout_s=180)
    out["snapshot"] = snapshot

    r_click = req("POST", f"/api/teaching/session/{session_id}/conversation", json={"message": "click the blue Sign In button"})
    out["click_msg_status"] = r_click.status_code
    out["click_msg_reply"] = (r_click.json() or {}).get("reply") if r_click.status_code == 200 else r_click.text

    click_step_id = ""
    click_step_title = ""
    if r_click.status_code == 200:
        ts = (r_click.json() or {}).get("teaching_session") or {}
        steps = ts.get("steps") or []
        if steps:
            last = steps[-1]
            click_step_id = str(last.get("id") or "")
            click_step_title = str(last.get("title") or "")
    out["click_step_id"] = click_step_id
    out["click_step_title"] = click_step_title

    if click_step_id:
        r_confirm_click = req("POST", f"/api/teaching/session/{session_id}/steps/{click_step_id}/confirm")
        out["confirm_click_status"] = r_confirm_click.status_code
        out["confirm_click_reply"] = (r_confirm_click.json() or {}).get("reply") if r_confirm_click.status_code == 200 else r_confirm_click.text

    r_review = req("POST", f"/api/teaching/session/{session_id}/review")
    out["review_status"] = r_review.status_code
    if r_review.status_code == 200:
        out["review_reply"] = (r_review.json() or {}).get("reply")

    r_approve = req("POST", f"/api/teaching/session/{session_id}/approve")
    out["approve_status"] = r_approve.status_code
    if r_approve.status_code == 200:
        approve_body = r_approve.json() or {}
        out["approve_reply"] = approve_body.get("reply")
        out["execution_readiness"] = approve_body.get("execution_readiness")
        out["warnings"] = approve_body.get("warnings")
        out["draft_result"] = approve_body.get("draft_result")

    r_next_q = req("GET", f"/api/teach-sessions/{session_id}/questions/next")
    out["next_question_status"] = r_next_q.status_code
    out["next_question_body"] = r_next_q.json() if r_next_q.status_code == 200 else r_next_q.text

    r_debug = req("GET", f"/api/teaching/session/{session_id}/debug")
    out["debug_status"] = r_debug.status_code
    out["debug_body"] = r_debug.json() if r_debug.status_code == 200 else r_debug.text

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
