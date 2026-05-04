from datetime import UTC, datetime
from typing import Optional

from conversational.teaching_conversation_models import TeachingConversationState


class TeachingConversationStore:
    def __init__(self) -> None:
        self._states: dict[str, TeachingConversationState] = {}

    def _key(self, tenant_id: str, workflow_id: str, session_id: str) -> str:
        return f"{tenant_id}:{workflow_id}:{session_id}"

    def get_or_create(self, tenant_id: str, workflow_id: str, session_id: str) -> TeachingConversationState:
        key = self._key(tenant_id=tenant_id, workflow_id=workflow_id, session_id=session_id)
        state = self._states.get(key)
        if state is not None:
            return state

        state = TeachingConversationState(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            session_id=session_id,
        )
        self._states[key] = state
        return state

    def update_state(
        self,
        state: TeachingConversationState,
        last_question_id: Optional[str] = None,
        unresolved_questions: Optional[int] = None,
    ) -> TeachingConversationState:
        state.turn_count += 1
        state.last_question_id = last_question_id
        if unresolved_questions is not None:
            state.unresolved_questions = unresolved_questions
        state.updated_at = datetime.now(UTC)
        return state


teaching_conversation_store = TeachingConversationStore()