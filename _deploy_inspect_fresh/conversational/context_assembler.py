import re

from conversational.execution_tracker import execution_tracker
from conversational.memory_models import AssembledContext
from conversational.memory_store import MemoryStore, memory_store


class ContextAssembler:
    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def extract_entities(self, message: str) -> list[str]:
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9_-]*\b", message or "")
        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    def assemble(self, tenant_id: str, session_id: str, user_message: str) -> AssembledContext:
        working_memory = self._store.get_working_memory(tenant_id=tenant_id, session_id=session_id, limit=20)
        episodes = self._store.search_episodes(tenant_id=tenant_id, session_id=session_id, query=user_message, limit=5)
        facts = self._store.get_facts(tenant_id=tenant_id, session_id=session_id, limit=20)
        entities = self.extract_entities(user_message)

        normalized_message = (user_message or "").lower()
        workflow_id: str | None = None
        if "health sherpa" in normalized_message or "smart sherpa" in normalized_message:
            workflow_id = "smart_sherpa_sync"
        elif "teach" in normalized_message or "watch me" in normalized_message or "learn this" in normalized_message:
            workflow_id = "teach_session"

        recent_executions: list[dict[str, object]] = []
        workflow_success_signal = 0.5
        if workflow_id:
            recent_records = execution_tracker.get_recent_for_workflow(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                limit=10,
            )
            recent_executions = [record.to_dict() for record in recent_records]
            workflow_success_signal = execution_tracker.get_workflow_success_signal(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
            )

        return AssembledContext(
            tenant_id=tenant_id,
            session_id=session_id,
            user_message=user_message,
            entities=entities,
            working_memory=working_memory,
            episodes=episodes,
            facts=facts,
            recent_executions=recent_executions,
            workflow_success_signal=workflow_success_signal,
        )


context_assembler = ContextAssembler(memory_store)
