from conversational.intent_router import RoutedIntent
from task_service import create_task_record


class ActionDispatcher:
    """Deterministic bridge from routed intent to existing Bill Core task queue."""

    _ALLOWED_WORKFLOWS = {"smart_sherpa_sync", "teach_session"}

    def dispatch(self, routed_intent: RoutedIntent, tenant_id: str, user_id: str) -> dict[str, str | None]:
        workflow_id = routed_intent.workflow_id
        fallback = {
            "action": "no_action",
            "task_id": None,
            "workflow_id": workflow_id,
        }

        if routed_intent.intent != "run_workflow":
            return fallback

        if not workflow_id or workflow_id not in self._ALLOWED_WORKFLOWS:
            return fallback

        try:
            task_payload = {
                "task_type": workflow_id,
                "workflow_name": workflow_id,
                "tenant_id": tenant_id,
                "requested_by_user_id": user_id,
            }
            task_record = create_task_record(task_payload)
            task_id = getattr(task_record, "id", None)
            if not task_id:
                return fallback

            return {
                "action": "task_queued",
                "task_id": task_id,
                "workflow_id": workflow_id,
            }
        except Exception:
            return fallback


action_dispatcher = ActionDispatcher()
