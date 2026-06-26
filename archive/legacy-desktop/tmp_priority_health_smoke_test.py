import os
from dotenv import load_dotenv
from modules.carriers.priority_health_worker import PriorityHealthWorker

load_dotenv()
worker = PriorityHealthWorker()

print({
    "carrier": "priority_health",
    "has_username": bool(worker.username),
    "has_password": bool(worker.password),
    "session_path": worker.session_path,
})

if not worker.username or not worker.password:
    print({"success": False, "error": "Missing PRIORITY_HEALTH_USERNAME or PRIORITY_HEALTH_PASSWORD"})
    raise SystemExit(0)

test_member = {
    "first_name": os.getenv("PRIORITY_HEALTH_TEST_FIRST_NAME", "").strip(),
    "last_name": os.getenv("PRIORITY_HEALTH_TEST_LAST_NAME", "").strip(),
    "dob": os.getenv("PRIORITY_HEALTH_TEST_DOB", "").strip(),
    "member_id": os.getenv("PRIORITY_HEALTH_TEST_MEMBER_ID", "").strip(),
    "policy_id": os.getenv("PRIORITY_HEALTH_TEST_POLICY_ID", "").strip(),
}

result = worker.run(test_member)
print({"result": result})
print(
    {
        "portal_ready": bool(result.get("portal_ready")),
        "member_inputs_present": any(str(v or "").strip() for v in test_member.values()),
    }
)
