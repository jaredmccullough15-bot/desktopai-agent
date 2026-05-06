from conversational.action_dispatcher import ActionDispatcher
from conversational.confidence_engine import ConfidenceEngine
from conversational.context_assembler import ContextAssembler
from conversational.conversation_service import ConversationService
from conversational.execution_tracker import execution_tracker
from conversational.intent_router import RoutedIntent
from conversational.memory_store import MemoryStore
from conversational.schemas import ConversationRequest


class FixedConfidenceEngine(ConfidenceEngine):
    def __init__(self, value: float) -> None:
        self._value = value

    def score(self, confidence_input):  # type: ignore[override]
        return self._value


class CapturingConfidenceEngine(ConfidenceEngine):
    def __init__(self, value: float) -> None:
        self._value = value
        self.last_input = None

    def score(self, confidence_input):  # type: ignore[override]
        self.last_input = confidence_input
        return self._value


class StaticRouter:
    def __init__(self, routed_intent: RoutedIntent) -> None:
        self._routed_intent = routed_intent

    def route(self, message: str) -> RoutedIntent:
        return self._routed_intent


class StubDispatcher:
    def __init__(self, result: dict[str, str | None]) -> None:
        self._result = result
        self.calls = 0

    def dispatch(self, routed_intent: RoutedIntent, tenant_id: str, user_id: str) -> dict[str, str | None]:
        self.calls += 1
        return self._result


def _service(router, confidence_engine, dispatcher) -> ConversationService:
    store = MemoryStore()
    assembler = ContextAssembler(store)
    return ConversationService(
        store=store,
        assembler=assembler,
        router=router,
        confidence_engine=confidence_engine,
        dispatcher=dispatcher,
    )


def test_smart_sherpa_high_confidence_queues_task() -> None:
    router = StaticRouter(
        RoutedIntent(intent="run_workflow", action="run_workflow", workflow_id="smart_sherpa_sync")
    )
    dispatcher = StubDispatcher(
        {
            "action": "task_queued",
            "task_id": "task-123",
            "workflow_id": "smart_sherpa_sync",
        }
    )
    service = _service(router, FixedConfidenceEngine(0.95), dispatcher)

    response = service.handle_message(
        ConversationRequest(tenant_id="tenant-1", session_id="user-1", message="run smart sherpa")
    )

    assert response.action == "task_queued"
    assert response.task_id == "task-123"
    assert dispatcher.calls == 1


def test_unknown_workflow_returns_route_only() -> None:
    router = StaticRouter(
        RoutedIntent(intent="run_workflow", action="run_workflow", workflow_id="unknown_workflow")
    )
    service = _service(router, FixedConfidenceEngine(0.95), ActionDispatcher())

    response = service.handle_message(
        ConversationRequest(tenant_id="tenant-1", session_id="user-1", message="run unknown workflow")
    )

    assert response.action == "route_only"
    assert response.task_id is None


def test_low_confidence_returns_route_only() -> None:
    router = StaticRouter(
        RoutedIntent(intent="run_workflow", action="run_workflow", workflow_id="smart_sherpa_sync")
    )
    dispatcher = StubDispatcher(
        {
            "action": "task_queued",
            "task_id": "task-999",
            "workflow_id": "smart_sherpa_sync",
        }
    )
    service = _service(router, FixedConfidenceEngine(0.20), dispatcher)

    response = service.handle_message(
        ConversationRequest(tenant_id="tenant-1", session_id="user-1", message="run smart sherpa")
    )

    assert response.action == "route_only"
    assert response.task_id is None
    assert dispatcher.calls == 0


def test_conversation_service_passes_workflow_signal_to_confidence_and_context_used() -> None:
    execution_tracker.records.clear()
    execution_tracker.log_execution(
        tenant_id="tenant-1",
        user_id="user-1",
        workflow_id="smart_sherpa_sync",
        task_id="seed-task",
        confidence=0.9,
        context_snapshot={},
        intent="run_workflow",
    )
    execution_tracker.mark_status(tenant_id="tenant-1", task_id="seed-task", status="completed")

    router = StaticRouter(
        RoutedIntent(intent="run_workflow", action="run_workflow", workflow_id="smart_sherpa_sync")
    )
    dispatcher = StubDispatcher(
        {
            "action": "task_queued",
            "task_id": "task-123",
            "workflow_id": "smart_sherpa_sync",
        }
    )
    confidence_engine = CapturingConfidenceEngine(0.95)
    service = _service(router, confidence_engine, dispatcher)

    response = service.handle_message(
        ConversationRequest(tenant_id="tenant-1", session_id="user-1", message="run smart sherpa")
    )

    assert response.action == "task_queued"
    assert confidence_engine.last_input is not None
    assert confidence_engine.last_input.historical_success_rate > 0.5

    latest = execution_tracker.get_recent(tenant_id="tenant-1", limit=1)[0]
    context_used = latest.context_snapshot.get("context_used", {})
    assert context_used.get("recent_executions", 0) >= 1
    assert context_used.get("workflow_success_signal", 0.0) > 0.5
