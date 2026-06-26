from pydantic import BaseModel


class RoutedIntent(BaseModel):
    intent: str
    action: str
    workflow_id: str | None = None


class IntentRouter:
    def route(self, message: str) -> RoutedIntent:
        lowered = (message or "").lower()

        if "health sherpa" in lowered or "smart sherpa" in lowered:
            return RoutedIntent(intent="run_workflow", action="run_workflow", workflow_id="smart_sherpa_sync")

        if "teach" in lowered or "watch me" in lowered or "learn this" in lowered:
            return RoutedIntent(intent="start_teach_session", action="start_teach_session", workflow_id="teach_session")

        if "what do you remember" in lowered:
            return RoutedIntent(intent="memory_query", action="memory_query", workflow_id=None)

        return RoutedIntent(intent="conversation", action="conversation", workflow_id=None)


intent_router = IntentRouter()
