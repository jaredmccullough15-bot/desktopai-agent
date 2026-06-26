import copy
import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

import main as m


def _approved_draft(*, draft_id: str = "draft-1", workflow_name: str = "trackvia_submission", include_start_url: bool = True) -> dict:
    first_step = {
        "id": "step-1",
        "step_order": 1,
        "step_name": "Open TrackVia",
        "action": "open_url" if include_start_url else "click_selector",
        "url": "https://go.trackvia.com/" if include_start_url else None,
        "selector": None if include_start_url else "button.start",
    }
    second_step = {
        "id": "step-2",
        "step_order": 2,
        "step_name": "Click search",
        "action": "click_selector",
        "selector": "button.search",
    }
    return {
        "draft_id": draft_id,
        "workflow_name": workflow_name,
        "review_status": "approved",
        "updated_at": datetime.utcnow().isoformat(),
        "steps": [first_step, second_step],
    }


class TaughtWorkflowRunEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(m.app)
        self._original_drafts = copy.deepcopy(m.workflow_learning_drafts)
        self.captured_payloads: list[dict] = []

        def _fake_create_task_record(payload: dict):
            self.captured_payloads.append(copy.deepcopy(payload))
            return {"id": "task-taught-1", "status": "queued"}

        self._task_patch = patch.object(m, "_create_task_record", side_effect=_fake_create_task_record)
        self._task_patch.start()
        m.workflow_learning_drafts.clear()

    def tearDown(self) -> None:
        self._task_patch.stop()
        m.workflow_learning_drafts.clear()
        m.workflow_learning_drafts.extend(self._original_drafts)

    def test_run_taught_approved_draft_loads(self):
        m.workflow_learning_drafts.append(_approved_draft())

        response = self.client.post("/api/workflows/trackvia_submission/run-taught", json={"mode": "interactive_visible", "payload": {}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")

    def test_run_taught_queues_taught_workflow(self):
        m.workflow_learning_drafts.append(_approved_draft())

        response = self.client.post("/api/workflows/trackvia_submission/run-taught", json={"mode": "interactive_visible", "payload": {}})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.captured_payloads)
        self.assertEqual(self.captured_payloads[0]["task_type"], "taught_workflow")

    def test_run_taught_payload_includes_action_plan(self):
        m.workflow_learning_drafts.append(_approved_draft())

        response = self.client.post("/api/workflows/trackvia_submission/run-taught", json={"mode": "interactive_visible", "payload": {}})

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(self.captured_payloads[0].get("action_plan"), list)
        self.assertGreaterEqual(len(self.captured_payloads[0]["action_plan"]), 2)

    def test_run_taught_first_navigate_uses_trackvia_url(self):
        m.workflow_learning_drafts.append(_approved_draft())

        response = self.client.post("/api/workflows/trackvia_submission/run-taught", json={"mode": "interactive_visible", "payload": {}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.captured_payloads[0]["start_url"], "https://go.trackvia.com/")

    def test_run_taught_missing_start_url_fails_explicitly(self):
        m.workflow_learning_drafts.append(_approved_draft(include_start_url=False))

        response = self.client.post("/api/workflows/trackvia_submission/run-taught", json={"mode": "interactive_visible", "payload": {}})

        self.assertEqual(response.status_code, 422)
        detail = response.json().get("detail", {})
        self.assertEqual(detail.get("message"), "Workflow is not runnable yet.")
        self.assertIn("No starting page was captured.", detail.get("blocking_reasons", []))

    def test_run_taught_non_client_workflow_requires_no_identity_fields(self):
        m.workflow_learning_drafts.append(_approved_draft(workflow_name="basic_portal_check"))

        response = self.client.post("/api/workflows/basic_portal_check/run-taught", json={"mode": "interactive_visible", "payload": {}})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "task-taught-1")


if __name__ == "__main__":
    unittest.main()
