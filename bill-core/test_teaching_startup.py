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

import uuid
from datetime import datetime
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
        assert data["teaching_session"] is not None
        assert data["teaching_session"]["status"] == "intro"
        assert data["teaching_session"]["workflow_name"] == "Test Workflow"
        assert data["teaching_session"]["workflow_summary"] is None
        assert data["teaching_session"]["steps"] == []
        assert data["reply"] is not None
        assert "started a teaching session" in data["reply"].lower()
        assert "quick explanation" in data["reply"].lower()

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
        assert "Is that correct?" in body["reply"]

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
