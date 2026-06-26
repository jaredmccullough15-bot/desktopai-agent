from conversational.task_understanding_service import TaskUnderstandingService, task_understanding_service
from conversational.task_understanding_store import TaskUnderstandingStore, task_understanding_store
from conversational.teaching_conversation_models import (
    TeachingChatRequest,
    TeachingChatResponse,
)
from conversational.teaching_conversation_store import TeachingConversationStore, teaching_conversation_store
from conversational.teaching_question_engine import TeachingQuestionEngine, teaching_question_engine


class TeachingConversationService:
    def __init__(
        self,
        task_service: TaskUnderstandingService,
        task_store: TaskUnderstandingStore,
        question_engine: TeachingQuestionEngine,
        conversation_store: TeachingConversationStore,
    ) -> None:
        self._task_service = task_service
        self._task_store = task_store
        self._question_engine = question_engine
        self._conversation_store = conversation_store

    def _build_reply(
        self,
        message: str,
        added_type: str,
        next_question: dict | None,
        was_answering_question: bool,
    ) -> str:
        _ = message
        if was_answering_question:
            lead = "Got it. I'll store that as part of the task logic."
        elif added_type == "step":
            lead = "Got it. I'll treat that as a step in the workflow."
        elif added_type == "edge_case":
            lead = "Got it. I'll treat that as an edge case Bill needs to handle."
        elif added_type == "decision":
            lead = "Got it. I'll store that as a decision point in this task."
        else:
            lead = "Got it. I'll store that as a rule for this task."

        if next_question is not None:
            return f"{lead} {next_question.get('question', '')}".strip()

        return f"{lead} I have enough structure for now: steps, decisions, and edge cases are covered."

    def chat(self, request: TeachingChatRequest) -> TeachingChatResponse:
        state = self._conversation_store.get_or_create(
            tenant_id=request.tenant_id,
            workflow_id=request.workflow_id,
            session_id=request.session_id,
        )

        self._task_store.create_or_get(
            tenant_id=request.tenant_id,
            workflow_id=request.workflow_id,
            task_name=request.task_name,
        )

        was_answering_question = bool(state.last_question_id)
        if was_answering_question and state.last_question_id:
            update_result = self._task_service.answer_question(
                tenant_id=request.tenant_id,
                workflow_id=request.workflow_id,
                question_id=state.last_question_id,
                answer=request.message,
            )
        else:
            update_result = self._task_service.record_teaching_note(
                tenant_id=request.tenant_id,
                workflow_id=request.workflow_id,
                note=request.message,
            )

        task = self._task_store.get(tenant_id=request.tenant_id, workflow_id=request.workflow_id)
        if task is None:
            task = self._task_store.create_or_get(
                tenant_id=request.tenant_id,
                workflow_id=request.workflow_id,
                task_name=request.task_name,
            )

        next_question_obj = self._question_engine.next_question(task)
        next_question = next_question_obj.model_dump(mode="json") if next_question_obj else None
        unresolved_questions = len([q for q in task.open_questions if not q.answered])
        state = self._conversation_store.update_state(
            state=state,
            last_question_id=next_question_obj.question_id if next_question_obj else None,
            unresolved_questions=unresolved_questions,
        )

        added_type = str(update_result.get("added_type") or "rule")
        reply = self._build_reply(
            message=request.message,
            added_type=added_type,
            next_question=next_question,
            was_answering_question=was_answering_question,
        )

        return TeachingChatResponse(
            reply=reply,
            task=task.model_dump(mode="json"),
            next_question=next_question,
            conversation_state=state.model_copy(deep=True),
        )


teaching_conversation_service = TeachingConversationService(
    task_service=task_understanding_service,
    task_store=task_understanding_store,
    question_engine=teaching_question_engine,
    conversation_store=teaching_conversation_store,
)