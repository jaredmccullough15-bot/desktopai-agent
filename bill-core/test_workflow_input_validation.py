"""
Tests for template-driven workflow input validation.

Covers the 5 cases specified in the validation refactoring spec:
  1. Teaching-created workflow with no required inputs can run without client fields.
  2. Client-based workflow with identity_required=True still requires identity fields.
  3. Workflow with required_inputs=['report_date'] requires only report_date.
  4. smart_sherpa_sync batch mode is still allowed without client identity.
  5. Missing required input returns clear error listing only that workflow's required fields.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

_MAIN_PATH = Path(__file__).resolve().parent / "main.py"
_SPEC = importlib.util.spec_from_file_location("bill_core_main_for_validation_tests", _MAIN_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"Unable to load module spec for {_MAIN_PATH}")

bill_main = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bill_main)


def _make_template(
    workflow_id: str = "test_workflow",
    required_inputs: list[str] | None = None,
    identity_required: bool = False,
    identity_fields: list[str] | None = None,
) -> "bill_main.TenantWorkflowTemplate":  # type: ignore[name-defined]
    """Build a minimal TenantWorkflowTemplate for testing."""
    from tenant_template_schemas import TenantWorkflowTemplate
    return TenantWorkflowTemplate(
        tenant_id="internal",
        workflow_id=workflow_id,
        workflow_name=workflow_id,
        required_inputs=required_inputs or [],
        identity_required=identity_required,
        identity_fields=identity_fields or [],
    )


class WorkflowInputValidationTests(unittest.TestCase):

    def test_teaching_created_workflow_no_required_inputs_runs_without_client_fields(self) -> None:
        """
        A teaching-created workflow (required_inputs=[], identity_required=False)
        should not raise even when no client identity fields are provided.
        """
        if not hasattr(bill_main, "_validate_workflow_run_inputs"):
            self.skipTest("_validate_workflow_run_inputs not available")

        template = _make_template(
            workflow_id="my_teaching_workflow",
            required_inputs=[],
            identity_required=False,
        )
        # Should not raise
        bill_main._validate_workflow_run_inputs(
            template,
            "my_teaching_workflow",
            source_record={},   # no identity fields
            target_contact={},
        )

    def test_client_workflow_with_identity_required_enforces_identity_fields(self) -> None:
        """
        A workflow with identity_required=True and explicit identity_fields
        must raise if those fields are missing from source_record.
        """
        if not hasattr(bill_main, "_validate_workflow_run_inputs"):
            self.skipTest("_validate_workflow_run_inputs not available")

        template = _make_template(
            workflow_id="bi_weekly_client_audit",
            identity_required=True,
            identity_fields=["client_name", "external_contact_id", "policy_number", "marketplace_id"],
        )
        with self.assertRaises(ValueError) as ctx:
            bill_main._validate_workflow_run_inputs(
                template,
                "bi_weekly_client_audit",
                source_record={},   # missing all identity fields
                target_contact={},
            )
        error_msg = str(ctx.exception)
        self.assertIn("bi_weekly_client_audit", error_msg)
        self.assertIn("requires these inputs before running", error_msg)
        # All four missing fields should appear in the message
        for field in ["client_name", "external_contact_id", "policy_number", "marketplace_id"]:
            self.assertIn(field, error_msg)

    def test_workflow_with_required_inputs_requires_only_those_fields(self) -> None:
        """
        A workflow with required_inputs=['report_date'] should require only
        report_date — not any identity fields.
        """
        if not hasattr(bill_main, "_validate_workflow_run_inputs"):
            self.skipTest("_validate_workflow_run_inputs not available")

        template = _make_template(
            workflow_id="monthly_report_workflow",
            required_inputs=["report_date"],
            identity_required=False,
        )
        # Missing report_date must raise
        with self.assertRaises(ValueError) as ctx:
            bill_main._validate_workflow_run_inputs(
                template,
                "monthly_report_workflow",
                source_record={},
                target_contact={},
            )
        error_msg = str(ctx.exception)
        self.assertIn("monthly_report_workflow", error_msg)
        self.assertIn("report_date", error_msg)

        # Providing report_date (in source_record) must NOT raise
        bill_main._validate_workflow_run_inputs(
            template,
            "monthly_report_workflow",
            source_record={"report_date": "2026-06-01"},
            target_contact={},
        )

    def test_smart_sherpa_batch_mode_allowed_without_client_identity(self) -> None:
        """
        smart_sherpa_sync run in batch mode must succeed even when client
        identity fields are absent.
        """
        if not hasattr(bill_main, "run_tenant_workflow"):
            self.skipTest("run_tenant_workflow not available")

        payload = {
            "workflow_id": "smart_sherpa_sync",
            "workflow_name": "smart_sherpa_sync",
            "run_mode": "batch",
            "source_record": {"run_mode": "batch"},
            "target_contact": {"run_mode": "batch"},
        }

        with patch.object(bill_main, "_resolve_workflow_id_for_tenant", side_effect=FileNotFoundError("no template")):
            result = bill_main.run_tenant_workflow(
                tenant_id="internal",
                workflow_id="smart_sherpa_sync",
                input_data=payload,
            )

        self.assertEqual(result.workflow_id, "smart_sherpa_sync")
        self.assertEqual(result.queued_task.status, "queued")

    def test_missing_required_input_error_names_only_that_workflow(self) -> None:
        """
        When a required input is missing the error must reference the specific
        workflow ID — not a generic 'source_record' label or a global field list.
        The error must NOT mention fields that are not in the workflow's required list.
        """
        if not hasattr(bill_main, "_validate_workflow_run_inputs"):
            self.skipTest("_validate_workflow_run_inputs not available")

        template = _make_template(
            workflow_id="export_workflow",
            required_inputs=["export_format"],
            identity_required=False,
        )
        with self.assertRaises(ValueError) as ctx:
            bill_main._validate_workflow_run_inputs(
                template,
                "export_workflow",
                source_record={},
                target_contact={},
            )
        error_msg = str(ctx.exception)
        self.assertIn("export_workflow", error_msg)
        self.assertIn("export_format", error_msg)
        # Must NOT mention unrelated global identity fields
        for global_field in ["client_name", "external_contact_id", "policy_number", "marketplace_id"]:
            self.assertNotIn(global_field, error_msg)


if __name__ == "__main__":
    unittest.main()
