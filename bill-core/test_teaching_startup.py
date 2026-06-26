#!/usr/bin/env python3
"""
Tests for Teaching Mode startup reliability.

Covers:
1. Brain command returns teaching_mode when workflow name is provided and worker is available
2. Brain command asks for workflow name when it's missing
3. GET /api/teaching/session/{id}/status returns the session record
4. POST /api/teaching/session/{id}/status transitions status to active/failed
5. Session status is browser_opening before worker calls back
6. Invalid status update is rejected
7. Unknown session_id returns 404
"""

import re
import json
import uuid
import importlib.util
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_machine(machine_uuid: str, online: bool = True, status: str = "idle") -> dict:
    return {
        "machine_uuid": machine_uuid,
        "machine_name": f"Worker-{machine_uuid[:6]}",
        "online": online,
        "status": status,
        "worker_version": "1.0.0",
        "execution_mode": "production",
        "last_seen": None,
    }


# ---------------------------------------------------------------------------
# Schemas unit tests
# ---------------------------------------------------------------------------

class TestTeachingStartupSchemas:
    def test_teaching_startup_state_defaults(self):
        from schemas import TeachingStartupState
        state = TeachingStartupState(
            session_id="abc",
            workflow_name="Test Workflow",
        )
        assert state.status == "browser_opening"
        assert state.overlay_enabled is True
        assert "Teaching mode is starting" in state.voice_prompt_text

    def test_teaching_startup_status_request_valid(self):
        from schemas import TeachingStartupStatusRequest
        req = TeachingStartupStatusRequest(status="active", message="Browser opened.")
        assert req.status == "active"

    def test_brain_command_response_has_teaching_mode_field(self):
        from schemas import BrainCommandResponse, TeachingStartupState
        state = TeachingStartupState(session_id="xyz", workflow_name="Demo")
        resp = BrainCommandResponse(
            recognized_intent="start_new_workflow",
            command="teach demo",
            before_execution="created draft",
            after_execution="started task 1",
            teaching_mode=state,
        )
        assert resp.teaching_mode is not None
        assert resp.teaching_mode.session_id == "xyz"

    def test_brain_command_response_teaching_mode_optional(self):
        from schemas import BrainCommandResponse
        resp = BrainCommandResponse(
            recognized_intent="worker_query",
            command="which worker is free",
            before_execution="checked workers",
            after_execution="worker A is free",
        )
        assert resp.teaching_mode is None


# ---------------------------------------------------------------------------
# In-memory store unit tests
# ---------------------------------------------------------------------------

class TestTeachingStartupStore:
    def setup_method(self):
        """Import the live in-memory store and clear it before each test."""
        import main as m
        self._m = m
        m._teaching_startup_sessions.clear()

    def test_store_is_empty_at_start(self):
        assert len(self._m._teaching_startup_sessions) == 0

    def test_session_record_written(self):
        sid = str(uuid.uuid4())
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        self._m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "task-1",
            "workflow_name": "Member Renewal",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "Teaching mode starting.",
            "created_at": now,
            "updated_at": now,
        }
        rec = self._m._teaching_startup_sessions[sid]
        assert rec["status"] == "browser_opening"

    def test_session_status_updated(self):
        sid = str(uuid.uuid4())
        from datetime import datetime
        now = datetime.utcnow().isoformat()
        self._m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "task-1",
            "workflow_name": "Member Renewal",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "",
            "created_at": now,
            "updated_at": now,
        }
        self._m._teaching_startup_sessions[sid]["status"] = "active"
        assert self._m._teaching_startup_sessions[sid]["status"] == "active"


# ---------------------------------------------------------------------------
# HTTP endpoint tests using FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_teaching_sessions():
    """Reset in-memory store before and after every test."""
    import main as m
    m._teaching_startup_sessions.clear()
    yield
    m._teaching_startup_sessions.clear()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    import main as m
    return TestClient(m.app)


class TestTeachingStatusEndpoints:
    def test_get_unknown_session_returns_404(self, client):
        res = client.get("/api/teaching/session/does-not-exist/status")
        assert res.status_code == 404

    def test_post_unknown_session_returns_404(self, client):
        res = client.post(
            "/api/teaching/session/does-not-exist/status",
            json={"status": "active", "message": "ok"},
        )
        assert res.status_code == 404

    def test_get_known_session_returns_record(self, client):
        import main as m
        from datetime import datetime
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "t-1",
            "workflow_name": "Test Flow",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "starting",
            "created_at": now,
            "updated_at": now,
        }
        res = client.get(f"/api/teaching/session/{sid}/status")
        assert res.status_code == 200
        data = res.json()
        assert data["session_id"] == sid
        assert data["status"] == "browser_opening"

    def test_post_transitions_to_active(self, client):
        import main as m
        from datetime import datetime
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "t-2",
            "workflow_name": "Renewal",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "",
            "created_at": now,
            "updated_at": now,
        }
        res = client.post(
            f"/api/teaching/session/{sid}/status",
            json={"status": "active", "task_id": "t-2", "message": "Browser opened."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "active"
        assert data["voice_prompt_text"] == "Teaching mode is active. Walk me through what this workflow is for."

        # Confirm GET also reflects the update
        get_res = client.get(f"/api/teaching/session/{sid}/status")
        assert get_res.json()["status"] == "active"

    def test_post_transitions_to_failed(self, client):
        import main as m
        from datetime import datetime
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "t-3",
            "workflow_name": "Renewal",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "",
            "created_at": now,
            "updated_at": now,
        }
        res = client.post(
            f"/api/teaching/session/{sid}/status",
            json={"status": "failed", "message": "Chrome not found."},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "failed"

    def test_post_invalid_status_rejected(self, client):
        import main as m
        from datetime import datetime
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": None,
            "workflow_name": "X",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "",
            "created_at": now,
            "updated_at": now,
        }
        res = client.post(
            f"/api/teaching/session/{sid}/status",
            json={"status": "in_progress"},
        )
        assert res.status_code == 422

    def test_status_is_browser_opening_before_worker_callback(self, client):
        """Teaching session must start as browser_opening — never active — until
        the worker explicitly calls back."""
        import main as m
        from datetime import datetime
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "t-4",
            "workflow_name": "Smoke Test",
            "status": "browser_opening",
            "overlay_enabled": True,
            "voice_prompt_text": "",
            "created_at": now,
            "updated_at": now,
        }
        res = client.get(f"/api/teaching/session/{sid}/status")
        assert res.json()["status"] == "browser_opening"


class TestCanonicalTeachingStartupEndpoints:
    def test_brain_command_returns_teaching_mode_and_queues_valid_payload(self, client):
        import main as m
        from schemas import MachineRecord

        captured: dict[str, dict] = {}

        def _fake_create_task(payload: dict):
            captured["payload"] = dict(payload)
            return m.TaskCreateResponse(id="task-brain-1", status="queued")

        worker = MachineRecord(
            machine_uuid="worker-uuid-1",
            machine_name="Worker-A",
            status="idle",
            worker_version="1.0.0",
            last_seen=datetime.utcnow().isoformat(),
            online=True,
            execution_mode="production",
            current_task_id=None,
            current_step=None,
        )

        with patch.object(m, "_create_task_record", side_effect=_fake_create_task), patch.object(
            m, "list_machines", return_value=[worker]
        ):
            res = client.post(
                "/api/brain/command",
                json={
                    "command": "start a new workflow called Claims Intake",
                    "target_machine_uuid": "worker-uuid-1",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["teaching_mode"] is not None
        assert data["teaching_mode"]["session_id"]
        assert captured["payload"]["task_type"] == "teach_session"
        assert captured["payload"]["draft_id"]
        assert captured["payload"]["session_id"]
        assert captured["payload"]["target_machine_uuid"] == "worker-uuid-1"

    def test_brain_command_includes_apprentice_teaching_session_intro(self, client):
        import main as m
        from schemas import MachineRecord

        def _fake_create_task(payload: dict):
            return m.TaskCreateResponse(id="task-brain-intro", status="queued")

        worker = MachineRecord(
            machine_uuid="worker-uuid-intro",
            machine_name="Worker-Intro",
            status="idle",
            worker_version="1.0.0",
            last_seen=datetime.utcnow().isoformat(),
            online=True,
            execution_mode="production",
            current_task_id=None,
            current_step=None,
        )

        with patch.object(m, "_create_task_record", side_effect=_fake_create_task), patch.object(
            m, "list_machines", return_value=[worker]
        ):
            res = client.post(
                "/api/brain/command",
                json={
                    "command": "Let's create a new workflow called Test Workflow",
                    "target_machine_uuid": "worker-uuid-intro",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["recognized_intent"] == "start_new_workflow"
        assert data["teaching_mode"] is not None
        assert data["teaching_session"] is not None
        assert data["teaching_session"]["status"] == "intro"
        assert data["teaching_session"]["workflow_name"] == "Test Workflow"
        assert data["teaching_session"]["workflow_summary"] is None
        assert data["teaching_session"]["steps"] == []
        assert data["reply"] is not None
        assert "started a teaching session" in data["reply"].lower()
        assert "quick explanation" in data["reply"].lower()
        assert data["voice_text"] == "Teaching mode is starting for Test Workflow. Once the browser opens, tell me what this workflow does."
        assert data["teaching_mode"]["voice_prompt_text"] == data["voice_text"]
        assert data["teaching_mode"]["target_machine_name"] == "Worker-Intro"
        assert data["reply"] == (
            "Sounds good. I started a teaching session for Test Workflow. "
            "Can you give me a quick explanation of what this workflow does?"
        )
        assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", data["voice_text"], re.IGNORECASE)
        assert "task-brain-intro" not in data["voice_text"]
        assert "session_id" not in data["voice_text"].lower()
        assert "task-brain-intro" not in data["reply"]

    def test_bill_chat_returns_teaching_mode_and_queues_valid_payload(self, client):
        import main as m
        from schemas import MachineRecord

        captured: dict[str, dict] = {}

        def _fake_create_task(payload: dict):
            captured["payload"] = dict(payload)
            return m.TaskCreateResponse(id="task-chat-1", status="queued")

        worker = MachineRecord(
            machine_uuid="worker-uuid-2",
            machine_name="Worker-B",
            status="idle",
            worker_version="1.0.0",
            last_seen=datetime.utcnow().isoformat(),
            online=True,
            execution_mode="production",
            current_task_id=None,
            current_step=None,
        )

        with patch.object(m, "_create_task_record", side_effect=_fake_create_task), patch.object(
            m, "list_machines", return_value=[worker]
        ):
            res = client.post(
                "/api/bill/chat",
                json={
                    "tenant_id": "internal",
                    "user_id": "u-1",
                    "session_id": "s-1",
                    "message": "start a new workflow called Enrollment Followup",
                    "target_machine_uuid": "worker-uuid-2",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["teaching_mode"] is not None
        assert data["session_id"]
        assert data["draft_id"]
        assert captured["payload"]["task_type"] == "teach_session"
        assert captured["payload"]["draft_id"]
        assert captured["payload"]["session_id"]
        assert captured["payload"]["target_machine_uuid"] == "worker-uuid-2"

    def test_missing_worker_does_not_queue_task(self, client):
        import main as m

        with patch.object(m, "_create_task_record", wraps=m._create_task_record) as create_task_mock, patch.object(
            m, "list_machines", return_value=[]
        ):
            res = client.post(
                "/api/bill/chat",
                json={
                    "tenant_id": "internal",
                    "user_id": "u-1",
                    "session_id": "s-1",
                    "message": "start a new workflow called Enrollment Followup",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["task_id"] is None
        assert data["next_required_input"] == "target_machine_uuid"
        create_task_mock.assert_not_called()

    def test_missing_workflow_name_asks_for_name(self, client):
        import main as m
        from schemas import MachineRecord

        worker = MachineRecord(
            machine_uuid="worker-uuid-3",
            machine_name="Worker-C",
            status="idle",
            worker_version="1.0.0",
            last_seen=datetime.utcnow().isoformat(),
            online=True,
            execution_mode="production",
            current_task_id=None,
            current_step=None,
        )

        with patch.object(m, "_create_task_record", wraps=m._create_task_record) as create_task_mock, patch.object(
            m, "list_machines", return_value=[worker]
        ):
            res = client.post(
                "/api/bill/chat",
                json={
                    "tenant_id": "internal",
                    "user_id": "u-1",
                    "session_id": "s-1",
                    "message": "start a new workflow",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert data["task_id"] is None
        assert data["next_required_input"] == "workflow_name"
        create_task_mock.assert_not_called()

    def test_bill_chat_response_shape_is_compatible(self, client):
        import main as m
        from schemas import MachineRecord

        def _fake_create_task(payload: dict):
            return m.TaskCreateResponse(id="task-chat-shape-1", status="queued")

        worker = MachineRecord(
            machine_uuid="worker-uuid-4",
            machine_name="Worker-D",
            status="idle",
            worker_version="1.0.0",
            last_seen=datetime.utcnow().isoformat(),
            online=True,
            execution_mode="production",
            current_task_id=None,
            current_step=None,
        )

        with patch.object(m, "_create_task_record", side_effect=_fake_create_task), patch.object(
            m, "list_machines", return_value=[worker]
        ):
            res = client.post(
                "/api/bill/chat",
                json={
                    "tenant_id": "internal",
                    "user_id": "u-1",
                    "session_id": "s-1",
                    "message": "start a new workflow called Renewal Outreach",
                    "target_machine_uuid": "worker-uuid-4",
                },
            )

        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert "intent" in data
        assert "action" in data
        assert "task_id" in data
        assert "workflow_id" in data
        assert "next_required_input" in data
        assert "metadata" in data
        assert "teaching_mode" in data


class TestTeachingConversationStepCapture:
    def _seed_session(self):
        import main as m
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "task-seed-1",
            "workflow_name": "Submission",
            "target_machine_uuid": "worker-1",
            "status": "active",
            "message": "Teaching browser opened.",
            "overlay_enabled": True,
            "voice_prompt_text": "Teach me.",
            "created_at": now,
            "updated_at": now,
            "teaching_session": {
                "session_id": sid,
                "workflow_name": "Submission",
                "workflow_summary": None,
                "status": "intro",
                "steps": [],
            },
        }
        return sid

    def test_summary_message_stores_workflow_summary(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["teaching_session"]["workflow_summary"] == "This workflow submits renewal applications for existing clients."
        assert "Where do we start?" in body["reply"]

    def test_first_action_message_creates_step_one(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "First I log into HealthSherpa and open the clients page."},
        )
        assert res.status_code == 200
        body = res.json()
        steps = body["teaching_session"]["steps"]
        assert len(steps) == 1
        assert steps[0]["order"] == 1
        assert steps[0]["title"] == "Open HealthSherpa clients page"
        assert steps[0]["employee_explanation"] == "First I log into HealthSherpa and open the clients page."
        assert steps[0]["bill_summary"]
        assert steps[0]["confirmed"] is False
        # New: reply contains an acknowledgment ack prefix (sophistication pass
        # replaced "Is that correct?" with confidence-tiered focused follow-ups)
        ack_variants = ("Got it", "Understood", "Makes sense", "Noted")
        assert any(ack in body["reply"] for ack in ack_variants), (
            f"Expected reply to start with an ack variant, got: {body['reply'][:120]}"
        )

    def test_confirm_endpoint_marks_step_confirmed(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        action_res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click Search and open the member profile."},
        )
        step_id = action_res.json()["teaching_session"]["steps"][0]["id"]

        confirm_res = client.post(f"/api/teaching/session/{sid}/steps/{step_id}/confirm")
        assert confirm_res.status_code == 200
        assert confirm_res.json()["teaching_session"]["steps"][0]["confirmed"] is True

    def test_vague_message_asks_for_clarification_and_no_step(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "okay"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["teaching_session"]["steps"] == []
        assert body["reply"] == "I need a little more detail. What action should Bill perform or watch for?"

    def test_decision_rule_attaches_to_latest_step(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Open the clients page and filter by renewal."},
        )
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Always verify the paid-through date before submitting."},
        )
        assert res.status_code == 200
        steps = res.json()["teaching_session"]["steps"]
        assert steps[0]["decision_rules"] == ["Always verify the paid-through date before submitting."]

    def test_exception_attaches_to_latest_step(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Open the clients page and filter by renewal."},
        )
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "If the member is missing DOB, stop and escalate."},
        )
        assert res.status_code == 200
        steps = res.json()["teaching_session"]["steps"]
        assert steps[0]["exceptions"] == ["If the member is missing DOB, stop and escalate."]


    def test_navigation_message_with_url_creates_navigate_action(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Navigate to https://go.trackvia.com/#/signin"},
        )

        assert res.status_code == 200
        body = res.json()
        step = body["teaching_session"]["steps"][0]
        assert step["order"] == 1
        assert step["employee_explanation"] == "Navigate to https://go.trackvia.com/#/signin"
        assert step["observed_actions"]
        action = step["observed_actions"][0]
        assert action["type"] == "navigate"
        assert action["url"] == "https://go.trackvia.com/#/signin"
        assert "trackvia" in step["title"].lower()

    def test_navigation_message_without_protocol_normalizes_to_https(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "go to google.com"},
        )

        assert res.status_code == 200
        action = res.json()["teaching_session"]["steps"][0]["observed_actions"][0]
        assert action["type"] == "navigate"
        assert action["url"] == "https://google.com"

    def test_click_sign_in_message_creates_click_step_with_label_fallback(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click the Sign In button"},
        )

        assert res.status_code == 200
        body = res.json()
        step = body["teaching_session"]["steps"][0]
        assert step["title"] == "Click Sign In"
        assert step["bill_summary"] == "Bill learned: click the Sign In button."
        assert step["observed_actions"]
        action = step["observed_actions"][0]
        assert action["type"] == "click"
        assert action["label"] == "Sign In"
        assert action["selector"]
        assert "has-text" in action["selector"]
        assert 0.7 <= float(step["bill_confidence"]) < 0.9
        assert (
            "Go ahead and click the Sign In button now. I'll watch and record it." in body["reply"]
            or "Go ahead and click Sign In now. I'll watch and record it." in body["reply"]
        )

    def test_click_blue_sign_in_message_creates_click_step(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click the blue Sign In button"},
        )

        assert res.status_code == 200
        action = res.json()["teaching_session"]["steps"][0]["observed_actions"][0]
        assert action["type"] == "click"
        assert action["label"] == "Sign In"
        assert action.get("target_label") == "Sign In"
        assert action.get("target_type") == "button"
        assert "blue" in list(action.get("descriptors") or [])
        selectors = list(action.get("selectors") or [])
        assert selectors
        assert all(", text=" not in str(selector).lower() for selector in selectors)
        import main as m
        assert all(m._is_valid_teaching_selector(str(selector)) for selector in selectors)

    @pytest.mark.parametrize(
        "message, expected_label, expected_type",
        [
            ("Click the Sign In button", "Sign In", "button"),
            ("Press the green Save button", "Save", "button"),
            ("Click the Email field", "Email", "field"),
            ("Click the Password field", "Password", "field"),
        ],
    )
    def test_click_target_extraction_variants(self, client, message, expected_label, expected_type):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": message},
        )
        assert res.status_code == 200
        action = res.json()["teaching_session"]["steps"][0]["observed_actions"][0]
        assert action.get("target_label") == expected_label
        assert action.get("target_type") == expected_type
        selectors = list(action.get("selectors") or [])
        assert selectors
        assert all(", text=" not in str(selector).lower() for selector in selectors)

    def test_click_selector_prefers_snapshot_target(self, client):
        import main as m

        sid = self._seed_session()
        record = m._teaching_startup_sessions[sid]
        record["teaching_session"]["page_context_snapshot"] = {
            "url": "https://go.trackvia.com/#/signin",
            "title": "Sign In",
            "visible_buttons": [
                {"text": "Sign In", "selector": "#signin-submit"},
            ],
            "visible_inputs": [],
            "visible_links": [],
            "visible_headings": [],
        }
        m._teaching_startup_sessions[sid] = record

        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click the blue Sign In button"},
        )
        assert res.status_code == 200
        action = res.json()["teaching_session"]["steps"][0]["observed_actions"][0]
        assert action.get("target_label") == "Sign In"
        assert action.get("selector") == "#signin-submit"
        assert action.get("selectors") and action.get("selectors")[0] == "#signin-submit"

    def test_click_message_with_provided_selector_stores_selector(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click the Sign In button selector: #sign-in-button"},
        )

        assert res.status_code == 200
        step = res.json()["teaching_session"]["steps"][0]
        action = step["observed_actions"][0]
        assert action["type"] == "click"
        assert action["label"] == "Sign In"
        assert action["selector"] == "#sign-in-button"
        assert float(step["bill_confidence"]) >= 0.9

    def test_click_step_appears_in_review_with_observed_action(self, client):
        sid = self._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow submits renewal applications for existing clients."},
        )
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click the Sign In button"},
        )

        review_res = client.post(f"/api/teaching/session/{sid}/review")
        assert review_res.status_code == 200
        review_steps = review_res.json()["review_summary"]["steps"]
        assert len(review_steps) == 1
        assert review_steps[0]["title"] == "Click Sign In"
        assert review_steps[0]["observed_actions"]
        assert review_steps[0]["observed_actions"][0]["type"] == "click"


class TestTeachingLanguageSophistication:
    @pytest.mark.parametrize(
        "message, expected_intent",
        [
            ("log into TrackVia", "authentication"),
            ("go to the upload dashboard", "navigation"),
            ("click pending uploads", "navigation"),
            ("search for the client", "search"),
            ("skip this one if it is missing", "decision_skip"),
            ("submit when everything looks right", "submission"),
            ("if it errors out just refresh", "recovery"),
            ("use the SSO login", "authentication"),
            ("download the report", "reporting"),
            ("wait for the queue to load", "waiting"),
        ],
    )
    def test_phrase_library_maps_employee_language_to_intents(self, message, expected_intent):
        import main as m

        analysis = m._analyze_teaching_message(message, [])
        assert expected_intent in analysis["intents"]
        assert analysis["title"]
        assert analysis["bill_summary"]

    def test_confidence_thresholds_drive_interrupt_behavior(self):
        import main as m

        high = m._analyze_teaching_message("Navigate to https://go.trackvia.com/#/signin", [])
        assert high["confidence"] >= 0.9
        assert high["should_interrupt"] is False

        medium = m._analyze_teaching_message("submit when everything looks right", [])
        assert 0.7 <= medium["confidence"] < 0.9

        low = m._analyze_teaching_message("do that", [])
        assert low["confidence"] < 0.7
        assert low["should_interrupt"] is True

    def test_followup_questions_are_focused(self):
        import main as m

        search = m._analyze_teaching_message("search for the client", [])
        assert "search" in str(search.get("followup_question") or "").lower()
        assert "client" in str(search.get("followup_question") or "").lower()

        submit = m._analyze_teaching_message("submit when everything looks right", [])
        assert "verify" in str(submit.get("followup_question") or "").lower()

        recovery = m._analyze_teaching_message("if it errors out just refresh", [])
        assert "next" in str(recovery.get("followup_question") or "").lower()

    def test_skip_phrase_is_classified_as_decision_skip_with_exception_context(self):
        import main as m

        analysis = m._analyze_teaching_message("skip if inactive", [])
        assert analysis["primary_intent"] == "decision_skip"
        assert analysis["exceptions"]

    def test_reply_style_varies_and_avoids_old_robotic_phrase(self, client):
        sid = TestTeachingConversationStepCapture()._seed_session()
        client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "This workflow processes reports."},
        )
        first = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "download the report"},
        )
        second = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "wait for the queue to load"},
        )
        first_reply = first.json()["reply"]
        second_reply = second.json()["reply"]
        assert "i'll treat that as" not in first_reply.lower()
        assert "i'll treat that as" not in second_reply.lower()
        assert first_reply != second_reply


class TestTeachingActionCapture:
    def _seed_session(self, steps: list[dict] | None = None):
        import main as m
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "task-actions-1",
            "workflow_name": "Submission",
            "target_machine_uuid": "worker-1",
            "status": "active",
            "message": "Teaching browser opened.",
            "overlay_enabled": True,
            "voice_prompt_text": "Teach me.",
            "created_at": now,
            "updated_at": now,
            "teaching_session": {
                "session_id": sid,
                "workflow_name": "Submission",
                "workflow_summary": "Workflow summary",
                "status": "teaching",
                "steps": steps or [],
            },
        }
        return sid

    def test_action_attaches_to_provided_step(self, client):
        step_a = {
            "id": "step-a",
            "order": 1,
            "title": "Open page",
            "employee_explanation": "Open the app",
            "bill_summary": "Open app",
            "decision_rules": [],
            "exceptions": [],
            "required_inputs": [],
            "confirmed": False,
            "observed_actions": [],
        }
        step_b = {
            "id": "step-b",
            "order": 2,
            "title": "Search member",
            "employee_explanation": "Search",
            "bill_summary": "Search",
            "decision_rules": [],
            "exceptions": [],
            "required_inputs": [],
            "confirmed": False,
            "observed_actions": [],
        }
        sid = self._seed_session([step_a, step_b])

        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "step_id": "step-a",
                "action": {
                    "id": "act-1",
                    "type": "click",
                    "label": "Search",
                    "selector": "button.search",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            },
        )

        assert res.status_code == 200
        steps = res.json()["teaching_session"]["steps"]
        assert len(steps[0]["observed_actions"]) == 1
        assert steps[0]["observed_actions"][0]["id"] == "act-1"
        assert steps[1]["observed_actions"] == []

    def test_action_attaches_to_latest_unconfirmed_step(self, client):
        steps = [
            {
                "id": "step-1",
                "order": 1,
                "title": "Open page",
                "employee_explanation": "",
                "bill_summary": "",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": True,
                "observed_actions": [],
            },
            {
                "id": "step-2",
                "order": 2,
                "title": "Search member",
                "employee_explanation": "",
                "bill_summary": "",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": False,
                "observed_actions": [],
            },
        ]
        sid = self._seed_session(steps)

        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "action": {
                    "id": "act-2",
                    "type": "click",
                    "label": "Next",
                    "selector": "button.next",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            },
        )

        assert res.status_code == 200
        updated = res.json()["teaching_session"]["steps"]
        assert updated[0]["observed_actions"] == []
        assert len(updated[1]["observed_actions"]) == 1

    def test_action_creates_temporary_step_when_none_exist(self, client):
        sid = self._seed_session([])

        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "action": {
                    "id": "act-3",
                    "type": "navigate",
                    "url": "https://example.com/members",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            },
        )

        assert res.status_code == 200
        steps = res.json()["teaching_session"]["steps"]
        assert len(steps) == 1
        assert steps[0]["title"] == "Observed browser activity"
        assert len(steps[0]["observed_actions"]) == 1

    def test_type_action_value_is_always_redacted(self, client):
        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Enter data",
                "employee_explanation": "",
                "bill_summary": "",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": False,
                "observed_actions": [],
            }
        ])

        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "action": {
                    "id": "act-4",
                    "type": "type",
                    "label": "Member ID",
                    "selector": "input.member-id",
                    "value_redacted": "12345",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            },
        )

        assert res.status_code == 200
        action = res.json()["teaching_session"]["steps"][0]["observed_actions"][0]
        assert action["value_redacted"] == "[redacted]"

    def test_sensitive_label_masks_selector_and_label(self, client):
        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Enter data",
                "employee_explanation": "",
                "bill_summary": "",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": False,
                "observed_actions": [],
            }
        ])

        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "action": {
                    "id": "act-5",
                    "type": "click",
                    "label": "MFA code",
                    "selector": "input#mfa-code",
                    "timestamp": datetime.utcnow().isoformat(),
                },
            },
        )

        assert res.status_code == 200
        action = res.json()["teaching_session"]["steps"][0]["observed_actions"][0]
        assert action["label"] == "[sensitive]"
        assert action["selector"] is None
        assert action["value_redacted"] == "[redacted]"


class TestTeachingReviewApproveContinue:
    def _seed_session(self, steps: list[dict] | None = None, draft_id: str | None = None):
        import main as m
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "task-review-1",
            "draft_id": draft_id,
            "workflow_name": "Submission",
            "target_machine_uuid": "worker-1",
            "status": "active",
            "message": "Teaching browser opened.",
            "overlay_enabled": True,
            "voice_prompt_text": "Teach me.",
            "created_at": now,
            "updated_at": now,
            "teaching_session": {
                "session_id": sid,
                "workflow_name": "Submission",
                "workflow_summary": "Workflow summary",
                "status": "teaching",
                "steps": steps or [],
            },
        }
        return sid

    def test_review_sets_status_review(self, client):
        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Open page",
                "employee_explanation": "Open dashboard",
                "bill_summary": "Open dashboard",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": True,
                "observed_actions": [],
            }
        ])

        res = client.post(f"/api/teaching/session/{sid}/review")
        assert res.status_code == 200
        payload = res.json()
        assert payload["teaching_session"]["status"] == "review"

    def test_review_summary_includes_steps(self, client):
        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Open page",
                "employee_explanation": "Open dashboard",
                "bill_summary": "Open dashboard",
                "decision_rules": ["Confirm account"],
                "exceptions": ["Escalate if blocked"],
                "required_inputs": ["member_id"],
                "confirmed": False,
                "observed_actions": [
                    {
                        "id": "a-1",
                        "type": "navigate",
                        "label": "Dashboard",
                        "url": "https://example.com/dashboard",
                        "selector": None,
                        "value_redacted": None,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ],
            }
        ])

        res = client.post(f"/api/teaching/session/{sid}/review")
        assert res.status_code == 200
        summary = res.json()["review_summary"]
        assert summary["total_steps"] == 1
        assert len(summary["steps"]) == 1
        assert summary["steps"][0]["title"] == "Open page"

    def test_approve_fails_if_no_steps(self, client):
        sid = self._seed_session([])
        res = client.post(f"/api/teaching/session/{sid}/approve")
        assert res.status_code == 400

    def test_approve_warns_on_unconfirmed_steps(self, client):
        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Open page",
                "employee_explanation": "Open dashboard",
                "bill_summary": "Open dashboard",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": False,
                "observed_actions": [],
            }
        ])

        res = client.post(f"/api/teaching/session/{sid}/approve")
        assert res.status_code == 200
        warnings = res.json()["warnings"]
        assert "Some steps are not confirmed yet. You can approve anyway, but Bill may need more training." in warnings

    def test_approve_creates_or_updates_draft(self, client):
        import main as m
        m.workflow_learning_drafts.clear()

        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Open page",
                "employee_explanation": "Open dashboard",
                "bill_summary": "Open dashboard",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": ["member_id"],
                "confirmed": True,
                "observed_actions": [
                    {
                        "id": "a-1",
                        "type": "navigate",
                        "label": "Dashboard",
                        "url": "https://example.com/dashboard",
                        "selector": None,
                        "value_redacted": None,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ],
            }
        ])

        create_res = client.post(f"/api/teaching/session/{sid}/approve")
        assert create_res.status_code == 200
        draft_result = create_res.json()["draft_result"]
        created_draft_id = draft_result["draft_id"]
        assert created_draft_id
        assert any(str(d.get("draft_id") or "") == created_draft_id for d in m.workflow_learning_drafts)

        sid2 = self._seed_session([
            {
                "id": "step-2",
                "order": 1,
                "title": "Search member",
                "employee_explanation": "Search by member id",
                "bill_summary": "Search member",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": ["member_id"],
                "confirmed": True,
                "observed_actions": [],
            }
        ], draft_id=created_draft_id)

        update_res = client.post(f"/api/teaching/session/{sid2}/approve")
        assert update_res.status_code == 200
        assert update_res.json()["draft_result"]["draft_id"] == created_draft_id


    def test_approve_navigation_url_step_is_runnable_and_run_taught_uses_start_url(self, client, monkeypatch):
        import main as m

        m.workflow_learning_drafts.clear()
        captured_payloads: list[dict] = []

        def _fake_create_task_record(payload):
            captured_payloads.append(dict(payload))
            return {"id": "task-url-run", "status": "queued"}

        monkeypatch.setattr(m, "_create_task_record", _fake_create_task_record)

        sid = self._seed_session([
            {
                "id": "step-url",
                "order": 1,
                "title": "Navigate to trackvia.com sign-in page",
                "employee_explanation": "Navigate to https://go.trackvia.com/#/signin",
                "bill_summary": "You start by opening https://go.trackvia.com/#/signin.",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": True,
                "observed_actions": [
                    {
                        "id": "a-url",
                        "type": "navigate",
                        "label": "Open go.trackvia.com",
                        "url": "https://go.trackvia.com/#/signin",
                        "selector": None,
                        "value_redacted": None,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ],
            }
        ])

        approve_res = client.post(f"/api/teaching/session/{sid}/approve")
        assert approve_res.status_code == 200
        readiness = approve_res.json()["execution_readiness"]
        assert readiness["has_start_url"] is True
        assert readiness["start_url"] == "https://go.trackvia.com/#/signin"
        assert readiness["runnable"] is True
        assert readiness["blocking_reasons"] == []

        draft_id = approve_res.json()["draft_result"]["draft_id"]
        run_res = client.post(f"/api/workflows/{draft_id}/run-taught", json={})
        assert run_res.status_code == 200
        assert captured_payloads
        assert captured_payloads[0]["task_type"] == "taught_workflow"
        assert captured_payloads[0]["start_url"] == "https://go.trackvia.com/#/signin"
        assert captured_payloads[0]["action_plan"][0]["action"] in {"navigate", "open_url"}
        assert captured_payloads[0]["action_plan"][0]["url"] == "https://go.trackvia.com/#/signin"

    def test_approve_click_step_includes_click_action_in_saved_draft(self, client):
        import main as m

        m.workflow_learning_drafts.clear()
        sid = self._seed_session([
            {
                "id": "step-click",
                "order": 1,
                "title": "Click Sign In",
                "employee_explanation": "Click the Sign In button",
                "bill_summary": "Bill learned: click the Sign In button.",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": True,
                "observed_actions": [
                    {
                        "id": "a-click",
                        "type": "click",
                        "label": "Sign In",
                        "selector": "button:has-text(\"Sign In\")",
                        "url": None,
                        "value_redacted": None,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                ],
            }
        ])

        approve_res = client.post(f"/api/teaching/session/{sid}/approve")
        assert approve_res.status_code == 200
        draft_id = approve_res.json()["draft_result"]["draft_id"]
        draft = next((item for item in m.workflow_learning_drafts if str(item.get("draft_id")) == str(draft_id)), None)
        assert draft is not None
        steps = draft.get("steps") or []
        assert steps
        assert steps[0]["action"] == "click_selector"
        assert steps[0]["selector"] == "button:has-text(\"Sign In\")"

    def test_continue_sets_teaching_status(self, client):
        sid = self._seed_session([
            {
                "id": "step-1",
                "order": 1,
                "title": "Open page",
                "employee_explanation": "Open dashboard",
                "bill_summary": "Open dashboard",
                "decision_rules": [],
                "exceptions": [],
                "required_inputs": [],
                "confirmed": True,
                "observed_actions": [],
            }
        ])

        client.post(f"/api/teaching/session/{sid}/review")
        res = client.post(f"/api/teaching/session/{sid}/continue")
        assert res.status_code == 200
        assert res.json()["teaching_session"]["status"] == "teaching"


class TestTeachingCopilotPhase1:
    def _seed_session(self, workflow_summary: str | None = "Existing summary"):
        import main as m
        sid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[sid] = {
            "session_id": sid,
            "task_id": "task-copilot-1",
            "workflow_name": "Submission",
            "target_machine_uuid": "worker-1",
            "status": "active",
            "message": "Teaching browser opened.",
            "overlay_enabled": True,
            "voice_prompt_text": "Teach me.",
            "created_at": now,
            "updated_at": now,
            "teaching_session": {
                "session_id": sid,
                "workflow_name": "Submission",
                "workflow_summary": workflow_summary,
                "status": "teaching",
                "steps": [],
            },
        }
        return sid

    def test_page_context_snapshot_redacts_sensitive_inputs(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/page-context",
            json={
                "url": "https://go.trackvia.com/#/signin",
                "title": "Sign In",
                "buttons": ["Sign In", "Forgot Password"],
                "inputs": [
                    {"label": "Email", "placeholder": "you@example.com", "type": "email"},
                    {"label": "Password", "placeholder": "Enter password", "type": "password"},
                ],
                "active_element": {"type": "input", "label": "Password"},
                "recent_type_field": "Email",
            },
        )
        assert res.status_code == 200
        snap = res.json()["teaching_session"]["page_context_snapshot"]
        assert snap["inputs"][0]["label"] == "[redacted]"
        assert snap["inputs"][1]["label"] == "[redacted]"
        assert snap["active_element"]["label"] == "[redacted]"
        assert snap["recent_type_field"] == "[redacted]"

    def test_sign_in_click_creates_meaningful_summary(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "action": {
                    "id": "a-1",
                    "type": "click",
                    "label": "Sign In",
                    "selector": "button:has-text(\"Sign In\")",
                    "url": None,
                    "value_redacted": None,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert "I saw you click Sign In" in (body.get("copilot_notice") or "")
        assert "login form" in (body.get("copilot_interpretation") or "").lower()

    def test_login_sequence_visible_in_status_poll_with_redaction(self, client):
        sid = self._seed_session()

        context_res = client.post(
            f"/api/teaching/session/{sid}/context",
            json={
                "url": "https://go.trackvia.com/#/signin",
                "title": "TrackVia Sign In",
                "visible_buttons": [{"text": "Sign In", "role": "button"}],
                "visible_inputs": [
                    {"label": "Email", "placeholder": "you@example.com", "type": "email", "name": "email"},
                    {"label": "Password", "placeholder": "Password", "type": "password", "name": "password"},
                ],
                "reason": "navigation",
            },
        )
        assert context_res.status_code == 200

        sequence = [
            {
                "id": "nav-1",
                "type": "navigate",
                "label": "TrackVia Sign In",
                "selector": None,
                "url": "https://go.trackvia.com/#/signin",
                "value_redacted": None,
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "id": "type-1",
                "type": "type",
                "label": "Email",
                "selector": "input[name='email']",
                "url": "https://go.trackvia.com/#/signin",
                "value_redacted": "[redacted]",
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "id": "type-2",
                "type": "type",
                "label": "Password",
                "selector": "input[name='password']",
                "url": "https://go.trackvia.com/#/signin",
                "value_redacted": "[redacted]",
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "id": "click-1",
                "type": "click",
                "label": "Sign In",
                "selector": "button:has-text(\"Sign In\")",
                "url": "https://go.trackvia.com/#/signin",
                "value_redacted": None,
                "timestamp": datetime.utcnow().isoformat(),
            },
            {
                "id": "submit-1",
                "type": "submit",
                "label": "Sign In form",
                "selector": "form#signin",
                "url": "https://go.trackvia.com/#/signin",
                "value_redacted": None,
                "timestamp": datetime.utcnow().isoformat(),
            },
        ]

        click_response = None
        for action in sequence:
            res = client.post(f"/api/teaching/session/{sid}/actions", json={"action": action})
            assert res.status_code == 200
            if action["type"] == "click":
                click_response = res

        assert click_response is not None
        click_body = click_response.json()
        assert "I saw you click Sign In" in (click_body.get("copilot_notice") or "")

        status_res = client.get(f"/api/teaching/session/{sid}/status")
        assert status_res.status_code == 200
        status_body = status_res.json()
        teaching_session = status_body.get("teaching_session") or {}
        steps = teaching_session.get("steps") or []
        assert steps

        actions = steps[-1].get("observed_actions") or []
        types = [a.get("type") for a in actions]
        assert "navigate" in types
        assert "type" in types
        assert "click" in types
        assert "submit" in types

        click_actions = [a for a in actions if a.get("type") == "click"]
        assert any((a.get("label") or "").lower() == "sign in" for a in click_actions)

        type_actions = [a for a in actions if a.get("type") == "type"]
        assert type_actions
        for a in type_actions:
            # No raw selector leaks for sensitive typed fields.
            assert a.get("selector") in (None, "")
            assert a.get("value_redacted") == "[redacted]"

        # Make sure no raw credential-like values leak through action labels.
        leaked_labels = " ".join(str(a.get("label") or "") for a in actions).lower()
        assert "input[name='password']" not in leaked_labels
        assert "you@example.com" not in leaked_labels

    def test_login_click_triggers_useful_question(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/actions",
            json={
                "action": {
                    "id": "a-2",
                    "type": "click",
                    "label": "Sign In",
                    "selector": "#signin",
                    "url": None,
                    "value_redacted": None,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            },
        )
        assert res.status_code == 200
        question = (res.json().get("copilot_question") or "").lower()
        assert "always required" in question or "logged in" in question

    def test_repeated_clicks_do_not_spam_questions(self, client):
        sid = self._seed_session()
        payload = {
            "action": {
                "id": "a-3",
                "type": "click",
                "label": "Sign In",
                "selector": "#signin",
                "url": None,
                "value_redacted": None,
                "timestamp": datetime.utcnow().isoformat(),
            }
        }
        first = client.post(f"/api/teaching/session/{sid}/actions", json=payload)
        second = client.post(f"/api/teaching/session/{sid}/actions", json=payload)
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json().get("copilot_question")
        assert second.json().get("copilot_question") in (None, "")

    def test_click_that_button_resolves_to_recent_sign_in(self, client):
        import main as m
        sid = self._seed_session()
        record = m._teaching_startup_sessions[sid]
        record["teaching_session"]["page_context_snapshot"] = {
            "url": "https://go.trackvia.com/#/signin",
            "title": "Sign In",
            "buttons": ["Sign In"],
            "inputs": [],
            "links": [],
            "headings": ["Welcome"],
            "active_element": None,
            "recent_click_label": "Sign In",
            "recent_type_field": None,
            "modal_present": False,
            "modal_title": None,
        }
        m._teaching_startup_sessions[sid] = record

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "click that button"},
        )
        assert res.status_code == 200
        steps = res.json()["teaching_session"]["steps"]
        assert steps
        assert "sign in" in steps[-1]["title"].lower()

    def test_ambiguous_reference_asks_clarification(self, client):
        import main as m
        sid = self._seed_session()
        record = m._teaching_startup_sessions[sid]
        record["teaching_session"]["page_context_snapshot"] = {
            "url": "https://go.trackvia.com/#/signin",
            "title": "Sign In",
            "buttons": ["Sign In", "Forgot Password"],
            "inputs": [],
            "links": ["Forgot Password"],
            "headings": [],
            "active_element": None,
            "recent_click_label": None,
            "recent_type_field": None,
            "modal_present": False,
            "modal_title": None,
        }
        m._teaching_startup_sessions[sid] = record

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "click that button"},
        )
        assert res.status_code == 200
        reply = res.json()["reply"].lower()
        assert "which button do you mean" in reply
        assert "sign in" in reply and "forgot password" in reply

    def test_click_sign_in_creates_step_or_manual_prompt(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click Sign In"},
        )
        assert res.status_code == 200
        reply = res.json()["reply"]
        assert (
            "recorded a click on Sign In as an executable step" in reply
            or "Go ahead and click Sign In now. I'll watch and record it." in reply
            or "Go ahead and click the Sign In button now. I'll watch and record it." in reply
        )

    def test_no_technical_selectors_shown_to_employee(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click the Sign In button selector: #sign-in-button"},
        )
        assert res.status_code == 200
        body = res.json()
        combined = " ".join(
            [
                body.get("reply") or "",
                body.get("copilot_notice") or "",
                body.get("copilot_interpretation") or "",
                body.get("copilot_question") or "",
            ]
        ).lower()
        assert "#sign-in-button" not in combined
        assert "button:has-text" not in combined

    def test_context_snapshot_bounds_lists(self, client):
        sid = self._seed_session()
        many_buttons = [{"text": f"Button {i}", "aria_label": "", "role": "button", "selector_hint": f"#b{i}"} for i in range(40)]
        many_inputs = [{"label": f"Field {i}", "placeholder": "", "type": "text", "name": f"f{i}", "selector_hint": f"#i{i}"} for i in range(40)]
        many_links = [{"text": f"Link {i}", "href": f"/l/{i}"} for i in range(40)]
        many_headings = [{"text": f"Heading {i}", "level": 2} for i in range(20)]

        res = client.post(
            f"/api/teaching/session/{sid}/context",
            json={
                "url": "https://example.com/app",
                "title": "Example",
                "visible_buttons": many_buttons,
                "visible_inputs": many_inputs,
                "visible_links": many_links,
                "visible_headings": many_headings,
            },
        )
        assert res.status_code == 200
        snap = res.json()["teaching_session"]["page_context_snapshot"]
        assert len(snap.get("visible_buttons") or []) == 20
        assert len(snap.get("visible_inputs") or []) == 20
        assert len(snap.get("visible_links") or []) == 20
        assert len(snap.get("visible_headings") or []) == 10

    def test_context_endpoint_stores_latest_and_history_max_5(self, client):
        import main as m
        sid = self._seed_session()
        for i in range(7):
            res = client.post(
                f"/api/teaching/session/{sid}/context",
                json={
                    "url": f"https://example.com/p/{i}",
                    "title": f"Page {i}",
                    "visible_buttons": [{"text": f"Button {i}", "aria_label": "", "role": "button", "selector_hint": f"#b{i}"}],
                },
            )
            assert res.status_code == 200

        stored = m._teaching_startup_sessions[sid]["teaching_session"]
        latest = stored.get("page_context_snapshot") or {}
        history = stored.get("page_context_history") or []
        assert latest.get("title") == "Page 6"
        assert len(history) == 5
        assert history[0].get("title") == "Page 2"
        assert history[-1].get("title") == "Page 6"

    def test_context_endpoint_persists_snapshot_in_debug_and_status(self, client):
        import main as m

        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/context",
            json={
                "url": "https://go.trackvia.com/#/signin",
                "title": "TrackVia Sign In",
                "visible_buttons": [
                    {"text": "Sign In", "aria_label": "", "role": "button", "selector_hint": "button:has-text(\"Sign In\")"},
                ],
                "visible_inputs": [
                    {"label": "Email", "placeholder": "you@example.com", "type": "email", "name": "email"},
                    {"label": "Password", "placeholder": "Password", "type": "password", "name": "password"},
                ],
                "visible_links": [{"text": "Forgot Password", "href": "/reset"}],
                "reason": "navigation",
            },
        )
        assert res.status_code == 200

        debug_res = client.get(f"/api/teaching/session/{sid}/debug")
        assert debug_res.status_code == 200
        debug_body = debug_res.json()
        assert debug_body["has_page_context_snapshot"] is True
        assert debug_body["page_context_button_count"] > 0
        assert debug_body["page_context_input_count"] > 0
        assert debug_body["page_context_history_count"] == 1

        status_res = client.get(f"/api/teaching/session/{sid}/status")
        assert status_res.status_code == 200
        status_body = status_res.json()
        snap = (status_body.get("teaching_session") or {}).get("page_context_snapshot") or {}
        assert snap.get("title") == "TrackVia Sign In"
        assert snap.get("visible_inputs")
        assert snap["visible_inputs"][0].get("label") == "[redacted]"
        assert snap["visible_inputs"][1].get("label") == "[redacted]"
        dumped = json.dumps(status_body).lower()
        assert "you@example.com" not in dumped
        assert "trackvia sign in" in dumped

        stored = m._teaching_startup_sessions[sid]["teaching_session"]
        assert stored.get("page_context_snapshot")
        assert len(stored.get("page_context_history") or []) == 1

    def test_context_endpoint_rejects_omnibox_snapshot(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/context",
            json={
                "url": "chrome-extension://omnibox-popup/index.html",
                "title": "Omnibox Popup | top-chrome",
                "visible_buttons": [{"text": "Search", "aria_label": "", "role": "button"}],
            },
        )
        assert res.status_code == 200
        assert (res.json().get("reply") or "") == "Invalid browser target ignored."
        snap = (res.json().get("teaching_session") or {}).get("page_context_snapshot") or {}
        assert snap.get("url") == ""
        assert snap.get("title") == "Bill is waiting for the real webpage tab."
        assert list(snap.get("visible_buttons") or []) == []
        assert str(snap.get("reason") or "") == "invalid_target_filtered"

    def test_debug_clears_existing_invalid_snapshot(self, client):
        import main as m

        sid = self._seed_session()
        record = m._teaching_startup_sessions[sid]
        record["teaching_session"]["page_context_snapshot"] = {
            "url": "chrome://omnibox-popup.top-chrome/",
            "title": "Omnibox Popup | top-chrome",
            "visible_buttons": [{"text": "Search"}],
        }
        record["teaching_session"]["page_context_history"] = [
            {
                "url": "chrome-extension://omnibox-popup/index.html",
                "title": "Omnibox Popup | top-chrome",
                "captured_at": "2026-05-20T10:10:20Z",
            },
            {
                "url": "https://go.trackvia.com/#/signin",
                "title": "TrackVia Sign In",
                "captured_at": "2026-05-20T10:10:40Z",
            },
        ]
        m._teaching_startup_sessions[sid] = record

        debug_res = client.get(f"/api/teaching/session/{sid}/debug")
        assert debug_res.status_code == 200
        body = debug_res.json()
        snap = body.get("page_context_snapshot") or {}
        assert snap.get("url") == ""
        assert snap.get("title") == "Bill is waiting for the real webpage tab."
        assert body.get("has_page_context_snapshot") is True
        history = body.get("page_context_history") or []
        assert len(history) == 1
        assert history[0].get("url") == "https://go.trackvia.com/#/signin"

    def test_click_that_button_uses_latest_visible_button_context(self, client):
        import main as m
        sid = self._seed_session()
        record = m._teaching_startup_sessions[sid]
        record["teaching_session"]["page_context_snapshot"] = {
            "url": "https://go.trackvia.com/#/signin",
            "title": "Sign In",
            "visible_buttons": [{"text": "Sign In", "aria_label": "", "role": "button", "selector_hint": "button:has-text(\"Sign In\")"}],
            "visible_inputs": [],
            "visible_links": [],
            "visible_headings": [],
        }
        m._teaching_startup_sessions[sid] = record

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "click that button"},
        )
        assert res.status_code == 200
        steps = res.json()["teaching_session"]["steps"]
        assert steps
        assert "sign in" in steps[-1]["title"].lower()

    def test_ambiguous_reference_with_button_and_link_asks_clarification(self, client):
        import main as m
        sid = self._seed_session()
        record = m._teaching_startup_sessions[sid]
        record["teaching_session"]["page_context_snapshot"] = {
            "url": "https://go.trackvia.com/#/signin",
            "title": "Sign In",
            "visible_buttons": [{"text": "Sign In", "aria_label": "", "role": "button", "selector_hint": "button:has-text(\"Sign In\")"}],
            "visible_links": [{"text": "Forgot Password", "href": "#forgot"}],
            "visible_inputs": [],
            "visible_headings": [],
        }
        m._teaching_startup_sessions[sid] = record

        res = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "click that button"},
        )
        assert res.status_code == 200
        reply = (res.json().get("reply") or "").lower()
        assert "do you mean the sign in button or the forgot password link" in reply

    def test_ui_bill_can_see_panel_does_not_render_selector_hint(self):
        page_tsx = Path(__file__).resolve().parents[1] / "bill-web" / "app" / "page.tsx"
        text = page_tsx.read_text(encoding="utf-8")
        assert "Bill can currently see" in text
        # Type declarations may include selector_hint, but render markup should not.
        ui_region = text[text.find("Bill can currently see"):text.find("Floating Chat Panel")]
        assert "selector_hint" not in ui_region

    def test_ui_bill_can_see_panel_masks_omnibox_context(self):
        page_tsx = Path(__file__).resolve().parents[1] / "bill-web" / "app" / "page.tsx"
        text = page_tsx.read_text(encoding="utf-8")
        ui_region = text[text.find("Bill can currently see"):text.find("Floating Chat Panel")]
        assert "Bill is waiting for the real webpage tab." in ui_region
        assert "Waiting for real webpage tab" in ui_region
        assert "omnibox-popup" in ui_region
        assert "top-chrome" in ui_region

    def test_extension_sensitive_field_metadata_is_minimized(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/extension-events",
            json={
                "event_type": "input",
                "current_url": "https://go.trackvia.com/#/signin",
                "domain": "go.trackvia.com",
                "target": {
                    "target_type": "field",
                    "target_label": "Password",
                    "selectors": ["#password", "input[name='password']"],
                    "selector_candidates": ["#password"],
                    "placeholder": "Enter password",
                    "name": "password",
                },
            },
        )
        assert res.status_code == 200
        body = res.json()
        event = (body.get("teaching_session") or {}).get("last_extension_event") or {}
        target = event.get("target") or {}
        assert target.get("target_type") in ("field", "input")
        assert target.get("target_label") in ("Password field", "Sensitive field")
        assert target.get("value_redacted") is True
        assert target.get("selectors") in (None, [])
        assert target.get("selector_candidates") in (None, [])

        steps = ((body.get("teaching_session") or {}).get("steps") or [])
        assert steps
        action = (steps[-1].get("observed_actions") or [])[-1]
        assert action.get("type") == "type"
        assert action.get("selector") in (None, "")
        assert action.get("value_redacted") == "[redacted]"
        dumped = json.dumps(body).lower()
        assert "#password" not in dumped
        assert "input[name='password']" not in dumped

    def test_extension_remains_observe_only_no_execution_calls(self):
        extension_root = Path(__file__).resolve().parents[1] / "chrome-extension" / "bill-teaching-assistant"
        content_js = (extension_root / "content.js").read_text(encoding="utf-8").lower()
        background_js = (extension_root / "background.js").read_text(encoding="utf-8").lower()
        merged = f"{content_js}\n{background_js}"

        assert "/api/teaching/session/" in merged
        assert "/extension-events" in merged
        assert "/api/brain/command" not in merged
        assert "/api/tasks" not in merged
        assert "/run-taught" not in merged
        assert ".click(" not in merged
        assert ".submit(" not in merged

    def test_context_payload_with_unexpected_shape_does_not_break_teaching_session(self, client):
        sid = self._seed_session()
        res = client.post(
            f"/api/teaching/session/{sid}/context",
            json={"url": "https://example.com", "visible_buttons": "invalid-shape"},
        )
        assert res.status_code == 200
        follow_up = client.post(
            f"/api/teaching/session/{sid}/conversation",
            json={"message": "Click Sign In"},
        )
        assert follow_up.status_code == 200

    def test_worker_context_post_failure_is_non_blocking(self):
        module_path = Path(__file__).resolve().parents[1] / "jarvis-platform" / "workers" / "bill-worker" / "teach_session.py"
        spec = importlib.util.spec_from_file_location("teach_session_under_test", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fake_resp = MagicMock()
        fake_resp.status_code = 500
        fake_resp.text = "server error"

        with patch.object(module.requests, "post", return_value=fake_resp):
            ok, err = module._post_teaching_context("http://localhost:8000", "session-1", {"url": "https://example.com"})

        assert ok is False
        assert err and "HTTP 500" in err


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
