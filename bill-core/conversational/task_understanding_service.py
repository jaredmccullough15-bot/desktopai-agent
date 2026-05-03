from typing import Any

from conversational.task_understanding_models import TaskOpenQuestion, TaskUnderstanding
from conversational.task_understanding_store import TaskUnderstandingStore, task_understanding_store
from conversational.teaching_question_engine import TeachingQuestionEngine, teaching_question_engine


class TaskUnderstandingService:
    def __init__(self, store: TaskUnderstandingStore, question_engine: TeachingQuestionEngine) -> None:
        self._store = store
        self._question_engine = question_engine

    def _serialize_task(self, task: TaskUnderstanding) -> dict[str, Any]:
        return task.model_dump(mode="json")

    def _serialize_question(self, question: TaskOpenQuestion | None) -> dict[str, Any] | None:
        if question is None:
            return None
        return question.model_dump(mode="json")

    def _response(self, task: TaskUnderstanding, added_type: str | None = None) -> dict[str, Any]:
        next_question = self._question_engine.next_question(task)
        response = {
            "task": self._serialize_task(task),
            "next_question": self._serialize_question(next_question),
        }
        if added_type is not None:
            response["added_type"] = added_type
        return response

    def start_teaching(self, tenant_id: str, workflow_id: str, task_name: str) -> dict[str, Any]:
        task = self._store.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=task_name)
        return self._response(task)

    def record_teaching_note(self, tenant_id: str, workflow_id: str, note: str) -> dict[str, Any]:
        task = self._store.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        lowered = (note or "").lower()
        added_type = "rule"

        if any(keyword in lowered for keyword in ("error", "fails", "wrong", "stuck", "missing", "timeout")):
            task = self._store.add_edge_case(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                situation=note,
                expected_response="Human reviews and recovers the workflow state.",
            )
            added_type = "edge_case"
        elif any(keyword in lowered for keyword in ("first", "start", "begin", "then", "next")):
            task = self._store.add_step(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                description=note,
            )
            added_type = "step"
        elif any(keyword in lowered for keyword in ("if", "when")):
            task = self._store.add_decision(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                question=note,
                condition=note,
            )
            added_type = "decision"
        else:
            task = self._store.add_rule(
                tenant_id=tenant_id,
                workflow_id=workflow_id,
                rule_text=note,
            )
            added_type = "rule"

        return self._response(task, added_type=added_type)

    def answer_question(
        self,
        tenant_id: str,
        workflow_id: str,
        question_id: str,
        answer: str,
    ) -> dict[str, Any]:
        self._store.answer_open_question(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            question_id=question_id,
            answer=answer,
        )
        # Preserve the answer as additional teaching signal in this phase.
        return self.record_teaching_note(
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            note=answer,
        )


task_understanding_service = TaskUnderstandingService(
    store=task_understanding_store,
    question_engine=teaching_question_engine,
)