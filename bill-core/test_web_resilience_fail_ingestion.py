from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from uuid import uuid4


_MAIN_PATH = Path(__file__).parent / "main.py"
_SPEC = importlib.util.spec_from_file_location("bill_core_main_for_web_resilience_fail_tests", _MAIN_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load module spec for {_MAIN_PATH}")

bill_main = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bill_main)


class WebResilienceFailIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.task_id = f"wr-phase2-{uuid4()}"
        self.machine_uuid = f"machine-{uuid4()}"
        self.task_record = {
            "id": self.task_id,
            "payload": {
                "task_type": "smart_sherpa_sync",
                "workflow_name": "smart_sherpa_sync",
            },
            "status": "in_progress",
            "assigned_machine_uuid": self.machine_uuid,
            "result_json": None,
            "error": None,
            "created_at": "2026-05-05T00:00:00",
            "updated_at": "2026-05-05T00:00:00",
            "completed_at": None,
            "logs": [],
        }
        bill_main.tasks.append(self.task_record)

    def tearDown(self) -> None:
        bill_main.tasks[:] = [task for task in bill_main.tasks if task.get("id") != self.task_id]

    def test_fail_endpoint_ingests_web_resilience_snapshot_and_exposes_recovery_context(self) -> None:
        page_state_snapshot = {
            "url": "https://www.healthsherpa.com/agents/example/clients?page=3",
            "title": "Clients - HealthSherpa",
            "visible_text_sample": "Client table with a blocking modal",
            "open_tab_count": 2,
            "timestamp": "2026-05-05T12:00:00",
        }
        detected_modals = ["[role=dialog]:Rate your experience"]
        detected_overlays = [".MuiBackdrop-root"]
        failed_action = "advance_page"
        attempted_fallbacks = [
            "empty_row_recovery",
            "return_to_list_via_site_control_or_url",
            "client_exception_recovery",
        ]

        payload = bill_main.TaskFailRequest(
            machine_uuid=self.machine_uuid,
            error="synthetic ingestion failure for web resilience regression test",
            result_json={
                "task_type": "smart_sherpa_sync",
                "web_resilience": {
                    "page_state_snapshot": page_state_snapshot,
                    "detected_modals": detected_modals,
                    "detected_overlays": detected_overlays,
                    "failed_action": failed_action,
                    "attempted_fallbacks": attempted_fallbacks,
                },
            },
        )

        fail_result = bill_main.fail_task(self.task_id, payload)
        self.assertEqual(fail_result.get("status"), "failed")

        stored_task = next(task for task in bill_main.tasks if task.get("id") == self.task_id)
        recovery_context = stored_task.get("recovery_context") or {}

        # 1) page_state_snapshot persisted
        self.assertIsInstance(recovery_context.get("page_state_snapshot"), dict)
        self.assertEqual(recovery_context.get("page_state_snapshot", {}).get("url"), page_state_snapshot["url"])

        # 2) detected_modals persisted
        self.assertEqual(recovery_context.get("detected_modals"), detected_modals)

        # 3) detected_overlays persisted
        self.assertEqual(recovery_context.get("detected_overlays"), detected_overlays)

        # 4) failed_action persisted
        self.assertEqual(recovery_context.get("failed_action"), failed_action)

        # 5) attempted_fallbacks persisted
        self.assertEqual(recovery_context.get("attempted_fallbacks"), attempted_fallbacks)

        # 6) audit event appended
        audit_events = stored_task.get("recovery_audit_trail") or []
        snapshot_events = [entry for entry in audit_events if entry.get("event_type") == "web_resilience_snapshot"]
        self.assertTrue(snapshot_events, "Expected web_resilience_snapshot audit event")
        latest_snapshot_event = snapshot_events[-1]
        self.assertEqual((latest_snapshot_event.get("details") or {}).get("failed_action"), failed_action)

        # 7) recovery-context endpoint returns fields
        recovery_response = bill_main.get_recovery_context(self.task_id)
        self.assertEqual((recovery_response.get("page_state_snapshot") or {}).get("url"), page_state_snapshot["url"])
        self.assertEqual(recovery_response.get("detected_modals"), detected_modals)
        self.assertEqual(recovery_response.get("detected_overlays"), detected_overlays)
        self.assertEqual(recovery_response.get("failed_action"), failed_action)
        self.assertEqual(recovery_response.get("attempted_fallbacks"), attempted_fallbacks)


if __name__ == "__main__":
    unittest.main()
