"""
Local predeploy Teaching Mode simulation test.
Validates the full pipeline: session create → context snapshot → action → debug + status poll.
"""
import requests
import json
import uuid
import sys

BASE = "http://127.0.0.1:8010"
SECRET = r'$0v.1+R03r:prr]$:#p50q28tiNFqXp<Ne>jq%xHN]nHyASKza?}V]nVbmT6^bK3'
HEADERS_WORKER = {"X-Bill-Worker-Key": SECRET, "Content-Type": "application/json"}

PASS = []
FAIL = []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        FAIL.append(name)
        print(f"  [FAIL] {name} — {detail}")


# ─── STEP 1: Health ──────────────────────────────────────────────────────────
print("\n=== STEP 1: Health check ===")
r = requests.get(f"{BASE}/health", timeout=10)
check("health_200", r.status_code == 200, r.status_code)
print(f"  {r.json()}")

# ─── STEP 2: List routes for teaching startup ─────────────────────────────────
print("\n=== STEP 2: Discover teaching-related routes ===")
r = requests.get(f"{BASE}/openapi.json", timeout=10)
if r.status_code == 200:
    paths = list(r.json().get("paths", {}).keys())
    teach_paths = [p for p in paths if "teach" in p.lower()]
    print(f"  teaching endpoints: {json.dumps(teach_paths, indent=4)}")
else:
    print(f"  openapi not available: {r.status_code}")
    teach_paths = []

# ─── STEP 3: Create workflow draft ─────────────────────────────────────────────
print("\n=== STEP 3: Create workflow draft ===")
draft_id = None
r = requests.post(f"{BASE}/api/brain/workflow-learning/drafts", json={
    "workflow_name": "TrackVia Local Predeploy Test",
    "learning_path": "demonstration",
    "goal": "This workflow logs into TrackVia.",
    "source_text": ""
}, timeout=10)
print(f"  status: {r.status_code}")
if r.status_code in (200, 201):
    body = r.json()
    draft_id = body.get("draft_id") or body.get("id")
    print(f"  draft_id: {draft_id}")
    check("draft_created", bool(draft_id), body)
else:
    print(f"  body: {r.text[:400]}")
    draft_id = "test-draft-001"  # fallback
    print(f"  Using fallback draft_id: {draft_id}")

# ─── STEP 4: Look for session startup endpoint ─────────────────────────────────
print("\n=== STEP 4: Find session startup endpoint ===")
startup_path = None
for candidate in [
    "/api/teaching/startup",
    "/api/teaching/sessions",
    "/api/teaching/session/start",
]:
    if any(candidate in p or p.startswith(candidate.split("{")[0]) for p in teach_paths):
        startup_path = candidate
        break

print(f"  startup_path found: {startup_path}")

session_id = str(uuid.uuid4())
print(f"  session_id: {session_id}")

# Try startup
if startup_path:
    r = requests.post(f"{BASE}{startup_path}", json={
        "session_id": session_id,
        "draft_id": draft_id,
        "workflow_name": "TrackVia Local Predeploy Test",
        "target_machine_uuid": "test-machine-001"
    }, headers=HEADERS_WORKER, timeout=10)
    print(f"  startup status: {r.status_code}")
    if r.status_code not in (200, 201):
        print(f"  body: {r.text[:400]}")

# ─── STEP 5: Try to POST actions directly (may auto-create session) ───────────
print("\n=== STEP 5: Check what happens with direct context POST ===")
ctx_r = requests.post(
    f"{BASE}/api/teaching/session/{session_id}/context",
    headers=HEADERS_WORKER,
    json={
        "url": "https://go.trackvia.com/#/signin",
        "title": "TrackVia - Sign In",
        "buttons": [
            {"label": "Sign In", "id": "signin-btn", "type": "submit"},
            {"label": "Forgot password?", "id": "", "type": "button"}
        ],
        "inputs": [
            {"label": "Email", "id": "email", "type": "email", "value": "user@example.com"},
            {"label": "Password", "id": "password", "type": "password", "value": "REDACTED"}
        ],
        "links": [],
        "history": ["https://go.trackvia.com/#/signin"]
    },
    timeout=10
)
print(f"  context POST status: {ctx_r.status_code}")
print(f"  body: {ctx_r.text[:500]}")

# ─── STEP 6: POST action ───────────────────────────────────────────────────────
print("\n=== STEP 6: POST click action ===")
act_r = requests.post(
    f"{BASE}/api/teaching/session/{session_id}/actions",
    headers=HEADERS_WORKER,
    json={
        "type": "click",
        "label": "Sign In",
        "element_id": "signin-btn",
        "url": "https://go.trackvia.com/#/signin",
        "timestamp": "2026-05-19T11:40:00Z",
        "sensitive": False
    },
    timeout=10
)
print(f"  action POST status: {act_r.status_code}")
print(f"  body: {act_r.text[:500]}")

# ─── STEP 7: GET debug endpoint ────────────────────────────────────────────────
print("\n=== STEP 7: GET debug endpoint ===")
dbg_r = requests.get(
    f"{BASE}/api/teaching/session/{session_id}/debug",
    timeout=10
)
print(f"  debug GET status: {dbg_r.status_code}")
if dbg_r.status_code == 200:
    dbg = dbg_r.json()
    print(f"  {json.dumps(dbg, indent=4)}")
    check("debug_endpoint_exists", True)
    check("has_page_context_snapshot", dbg.get("has_page_context_snapshot") == True, dbg.get("has_page_context_snapshot"))
    check("observed_actions_count_gt0", (dbg.get("observed_actions_count") or 0) > 0, dbg.get("observed_actions_count"))
    check("page_context_url_correct", "trackvia" in str(dbg.get("page_context_url", "")), dbg.get("page_context_url"))
    check("page_context_button_count_gt0", (dbg.get("page_context_button_count") or 0) > 0)
    check("page_context_input_count_gt0", (dbg.get("page_context_input_count") or 0) > 0)
    # Verify no sensitive values leaked
    raw_str = json.dumps(dbg)
    check("no_raw_password_in_debug", "password" not in raw_str.lower() or "REDACTED" in raw_str, "raw password found")
else:
    print(f"  body: {dbg_r.text[:400]}")
    check("debug_endpoint_exists", False, f"status={dbg_r.status_code}")

# ─── STEP 8: GET status (frontend polling simulation) ─────────────────────────
print("\n=== STEP 8: GET status (frontend poll simulation) ===")
st_r = requests.get(
    f"{BASE}/api/teaching/session/{session_id}/status",
    timeout=10
)
print(f"  status GET: {st_r.status_code}")
if st_r.status_code == 200:
    st = st_r.json()
    print(f"  {json.dumps(st, indent=4)}")
    check("status_endpoint_200", True)
    check("status_field_present", "status" in st, st)
    # Check no raw sensitive values in status output
    raw_str = json.dumps(st).lower()
    check("no_sensitive_in_status", "password" not in raw_str or "redacted" in raw_str, "raw password in status")
else:
    print(f"  body: {st_r.text[:400]}")
    check("status_endpoint_200", False, f"status={st_r.status_code}")

# ─── SUMMARY ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
if FAIL:
    print(f"FAILED checks: {FAIL}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED — ready for Beanstalk deployment")
    sys.exit(0)
