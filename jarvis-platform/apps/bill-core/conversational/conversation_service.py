from typing import Any

from conversational.action_dispatcher import ActionDispatcher, action_dispatcher
from conversational.confidence_engine import ConfidenceEngine, ConfidenceInput
from conversational.context_assembler import ContextAssembler, context_assembler
from conversational.execution_tracker import execution_tracker
from conversational.intent_router import IntentRouter, intent_router
from conversational.memory_models import WorkingMemoryTurn
from conversational.memory_store import MemoryStore, memory_store
from conversational.persona import BILL_PERSONA_PROMPT
from conversational.schemas import ConversationRequest, ConversationResponse


class ConversationService:
    def __init__(
        self,
        store: MemoryStore,
        assembler: ContextAssembler,
        router: IntentRouter,
        confidence_engine: ConfidenceEngine,
        dispatcher: ActionDispatcher,
    ) -> None:
        self._store = store
        self._assembler = assembler
        self._router = router
        self._confidence_engine = confidence_engine
        self._dispatcher = dispatcher

    def _build_reply(
        self,
        request: ConversationRequest,
        routed_intent: str,
        routed_action: str,
        workflow_id: str | None,
        confidence: float,
        entity_count: int,
        working_memory_count: int,
        response_action: str,
    ) -> str:
        if response_action == "task_queued" and workflow_id:
            return f"I'm routing this to the {workflow_id} workflow now."

        if routed_intent == "memory_query":
            return (
                f"Route selected: memory_query. I currently have {working_memory_count} working-memory turns "
                f"for tenant {request.tenant_id}, session {request.session_id}. "
                "Action remains route_only in Phase 1."
            )

        workflow_text = workflow_id or "none"
        return (
            f"Route selected: intent={routed_intent}, action={routed_action}, workflow_id={workflow_text}. "
            f"Confidence={confidence:.2f}, entities={entity_count}. "
            "Action remains route_only in Phase 1; no workflow execution is started yet."
        )

    def handle_message(self, request: ConversationRequest) -> ConversationResponse:
        self._store.add_turn(
            WorkingMemoryTurn(
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                role="user",
                message=request.message,
            )
        )

        context = self._assembler.assemble(
            tenant_id=request.tenant_id,
            session_id=request.session_id,
            user_message=request.message,
        )

        routed = self._router.route(request.message)

        confidence_input = ConfidenceInput(
            message=request.message,
            intent=routed.intent,
            workflow_id=routed.workflow_id,
            entity_count=len(context.entities),
            working_memory_turns=len(context.working_memory),
            historical_success_rate=context.workflow_success_signal,
        )
        confidence_score = self._confidence_engine.score(confidence_input)

        response_action = "route_only"
        task_id: str | None = None
        if confidence_score >= 0.80 and routed.intent == "run_workflow":
            try:
                dispatch_result: dict[str, Any] = self._dispatcher.dispatch(
                    routed_intent=routed,
                    tenant_id=request.tenant_id,
                    user_id=request.session_id,
                )
                if dispatch_result.get("action") == "task_queued":
                    response_action = "task_queued"
                    task_id = str(dispatch_result.get("task_id") or "") or None
                    if task_id and routed.workflow_id:
                        context_used = {
                            "entities": context.entities,
                            "facts": len(context.facts),
                            "episodes": len(context.episodes),
                            "recent_executions": len(context.recent_executions),
                            "workflow_success_signal": context.workflow_success_signal,
                        }
                        execution_tracker.log_execution(
                            tenant_id=request.tenant_id,
                            user_id=request.session_id,
                            workflow_id=routed.workflow_id,
                            task_id=task_id,
                            confidence=confidence_score,
                            intent=routed.intent,
                            context_snapshot={
                                **context_used,
                                "context_used": context_used,
                            },
                        )
            except Exception:
                response_action = "route_only"
                task_id = None

        reply = self._build_reply(
            request=request,
            routed_intent=routed.intent,
            routed_action=routed.action,
            workflow_id=routed.workflow_id,
            confidence=confidence_score,
            entity_count=len(context.entities),
            working_memory_count=len(context.working_memory),
            response_action=response_action,
        )

        self._store.add_turn(
            WorkingMemoryTurn(
                tenant_id=request.tenant_id,
                session_id=request.session_id,
                role="assistant",
                message=reply,
            )
        )

        return ConversationResponse(
            tenant_id=request.tenant_id,
            session_id=request.session_id,
            message=request.message,
            reply=reply,
            action=response_action,
            task_id=task_id,
            routed_intent=routed.intent,
            routed_action=routed.action,
            workflow_id=routed.workflow_id,
            confidence=confidence_score,
            should_execute=self._confidence_engine.should_execute(confidence_score),
            should_clarify=self._confidence_engine.should_clarify(confidence_score),
            should_escalate=self._confidence_engine.should_escalate(confidence_score),
            entities=context.entities,
        )


conversation_service = ConversationService(
    store=memory_store,
    assembler=context_assembler,
    router=intent_router,
    confidence_engine=ConfidenceEngine(),
    dispatcher=action_dispatcher,
)

_ = BILL_PERSONA_PROMPT
