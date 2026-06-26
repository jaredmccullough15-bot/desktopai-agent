import copy
from datetime import datetime
from uuid import uuid4

from fastapi.testclient import TestClient

import main as m


def _manual_only_draft(draft_id: str, workflow_name: str) -> dict:
    return {
        "draft_id": draft_id,
        "workflow_name": workflow_name,
        "review_status": "approved",
        "updated_at": datetime.utcnow().isoformat(),
        "steps": [
            {
                "step_order": 1,
                "step_name": "Search member",
                "action": "manual_step",
                "instruction": "Search by member id",
            }
        ],
    }


def _runnable_draft(draft_id: str, workflow_name: str) -> dict:
    return {
        "draft_id": draft_id,
        "workflow_name": workflow_name,
        "review_status": "approved",
        "updated_at": datetime.utcnow().isoformat(),
        "steps": [
            {
                "step_order": 1,
                "step_name": "Open TrackVia",
                "action": "open_url",
                "url": "https://go.trackvia.com/",
            },
            {
                "step_order": 2,
                "step_name": "Click login",
                "action": "click_selector",
                "selector": "button[type='submit']",
            },
        ],
    }


def test_validate_manual_only_draft_not_runnable() -> None:
    readiness = m.validate_taught_workflow_executable(_manual_only_draft("d1", "manual_only"))
    assert readiness["runnable"] is False
    assert readiness["executable_action_count"] == 0
    assert any("manual-only" in reason.lower() for reason in readiness["blocking_reasons"])


def test_validate_navigation_draft_runnable() -> None:
    readiness = m.validate_taught_workflow_executable(_runnable_draft("d2", "trackvia_demo"))
    assert readiness["runnable"] is True
    assert readiness["start_url"] == "https://go.trackvia.com/"


def test_approve_persists_execution_readiness() -> None:
    client = TestClient(m.app)
    original_sessions = copy.deepcopy(m._teaching_startup_sessions)
    original_drafts = copy.deepcopy(m.workflow_learning_drafts)
    m._teaching_startup_sessions.clear()
    m.workflow_learning_drafts.clear()
    try:
        session_id = str(uuid4())
        now = datetime.utcnow().isoformat()
        m._teaching_startup_sessions[session_id] = {
            "session_id": session_id,
            "task_id": "task-1",
            "workflow_name": "TrackVia Demo",
            "target_machine_uuid": "worker-1",
            "status": "active",
            "message": "Teaching browser opened.",
            "overlay_enabled": True,
            "voice_prompt_text": "Teach me.",
            "created_at": now,
            "updated_at": now,
            "teaching_session": {
                "session_id": session_id,
                "workflow_name": "TrackVia Demo",
                "workflow_summary": "Teach TrackVia flow",
                "status": "teaching",
                "steps": [
                    {
                        "id": "step-1",
                        "order": 1,
                        "title": "Open TrackVia",
                        "employee_explanation": "Open TrackVia",
                        "bill_summary": "Open TrackVia",
                        "decision_rules": [],
                        "exceptions": [],
                        "required_inputs": [],
                        "confirmed": True,
                        "observed_actions": [
                            {
                                "id": "a-1",
                                "type": "navigate",
                                "label": "TrackVia",
                                "url": "https://go.trackvia.com/",
                                "selector": None,
                                "value_redacted": None,
                                "timestamp": now,
                            }
                        ],
                    }
                ],
            },
        }

        res = client.post(f"/api/teaching/session/{session_id}/approve")
        assert res.status_code == 200
        body = res.json()
        readiness = body.get("execution_readiness") or {}
        assert readiness.get("runnable") is True
        draft_id = body.get("draft_result", {}).get("draft_id")
        draft = next((d for d in m.workflow_learning_drafts if str(d.get("draft_id") or "") == str(draft_id)), None)
        assert draft is not None
        assert bool((draft.get("execution_readiness") or {}).get("runnable")) is True
    finally:
        m._teaching_startup_sessions.clear()
        m._teaching_startup_sessions.update(original_sessions)
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.extend(original_drafts)


def test_publish_rejects_missing_start_url() -> None:
    client = TestClient(m.app)
    original_drafts = copy.deepcopy(m.workflow_learning_drafts)
    try:
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.append(_manual_only_draft("d3", "not_runnable_publish"))
        res = client.post("/api/brain/workflow-learning/drafts/d3/publish", json={})
        assert res.status_code == 422
        detail = res.json().get("detail") or {}
        assert "blocking_reasons" in detail
    finally:
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.extend(original_drafts)


def test_run_taught_rejects_missing_start_url() -> None:
    client = TestClient(m.app)
    original_drafts = copy.deepcopy(m.workflow_learning_drafts)
    try:
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.append(_manual_only_draft("d4", "not_runnable_run"))
        res = client.post("/api/workflows/not_runnable_run/run-taught", json={})
        assert res.status_code == 422
        detail = res.json().get("detail") or {}
        assert "blocking_reasons" in detail
    finally:
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.extend(original_drafts)


def test_run_taught_queues_when_runnable(monkeypatch) -> None:
    client = TestClient(m.app)
    original_drafts = copy.deepcopy(m.workflow_learning_drafts)
    created: list[dict] = []

    def _fake_create_task_record(payload):
        record = {"task_id": "task-runnable", "payload": payload}
        created.append(record)
        return {"id": "task-runnable", "status": "queued"}

    monkeypatch.setattr(m, "_create_task_record", _fake_create_task_record)
    try:
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.append(_runnable_draft("d5", "runnable_run"))
        res = client.post("/api/workflows/runnable_run/run-taught", json={"target_machine_uuid": "worker-1"})
        assert res.status_code == 200
        assert created
        payload = created[0]["payload"]
        assert payload.get("start_url") == "https://go.trackvia.com/"
        assert payload.get("target_machine_uuid") == "worker-1"
    finally:
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.extend(original_drafts)
