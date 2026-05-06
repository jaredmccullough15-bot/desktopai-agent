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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
