from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


_MAIN_PATH = Path(__file__).resolve().parent / "main.py"
_SPEC = importlib.util.spec_from_file_location("bill_core_main_for_smart_sherpa_tests", _MAIN_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load module spec for {_MAIN_PATH}")

bill_main = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bill_main)


class SmartSherpaRuntimeTests(unittest.TestCase):
    def test_batch_mode_normalization_enforces_strict_existing_page_flags(self) -> None:
        normalized = bill_main._ensure_smart_sherpa_batch_mode(
            {
                "workflow_id": "smart_sherpa_sync",
                "workflow_name": "smart_sherpa_sync",
                "task_type": "smart_sherpa_sync",
                "run_mode": "batch",
                "attach_to_existing": False,
                "require_existing_page": False,
                "allow_launch_fallback": True,
                "source_record": {"run_mode": "batch"},
                "target_contact": {"run_mode": "batch"},
            }
        )

        self.assertIs(normalized["attach_to_existing"], True)
        self.assertIs(normalized["require_existing_page"], True)
        self.assertIs(normalized["allow_launch_fallback"], False)
        self.assertEqual(normalized["browser_profile_policy"], "attach_existing_debug")

    def test_internal_smart_sherpa_missing_template_uses_compat_queue_path(self) -> None:
        if not hasattr(bill_main, "run_tenant_workflow"):
            self.skipTest("Tenant template runtime is not available in this environment")

        payload = {
            "workflow_id": "smart_sherpa_sync",
            "workflow_name": "smart_sherpa_sync",
            "run_mode": "batch",
            "source_record": {"run_mode": "batch"},
            "target_contact": {"run_mode": "batch"},
        }

        before_count = len(bill_main.tasks)
        with patch.object(bill_main, "_resolve_workflow_id_for_tenant", side_effect=FileNotFoundError("missing")):
            result = bill_main.run_tenant_workflow(
                tenant_id="internal",
                workflow_id="smart_sherpa_sync",
                input_data=payload,
            )

        self.assertEqual(result.workflow_id, "smart_sherpa_sync")
        self.assertEqual(result.queued_task.status, "queued")
        self.assertGreater(len(bill_main.tasks), before_count)

        queued_task = next(task for task in reversed(bill_main.tasks) if task.get("id") == result.task_id)
        queued_payload = dict(queued_task.get("payload") or {})
        self.assertIs(queued_payload.get("attach_to_existing"), True)
        self.assertIs(queued_payload.get("require_existing_page"), True)
        self.assertIs(queued_payload.get("allow_launch_fallback"), False)

    def test_non_batch_smart_sherpa_coerce_does_not_raise_without_identity(self) -> None:
        """Coercion no longer validates identity fields globally; validation is
        deferred to after the template is loaded in run_tenant_workflow()."""
        if not hasattr(bill_main, "_coerce_tenant_workflow_run_request"):
            self.skipTest("Tenant workflow coercion helper is not available")

        # Should NOT raise — global identity validation has been removed from coercion
        result = bill_main._coerce_tenant_workflow_run_request(
            "internal",
            "smart_sherpa_sync",
            {
                "workflow_id": "smart_sherpa_sync",
                "workflow_name": "smart_sherpa_sync",
                "run_mode": "client",
                "source_record": {},
                "target_contact": {},
            },
        )
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()
