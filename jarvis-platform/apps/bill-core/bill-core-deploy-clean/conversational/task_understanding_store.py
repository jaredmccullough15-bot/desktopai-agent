from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from conversational.task_understanding_models import (
    TaskDecision,
    TaskEdgeCase,
    TaskOpenQuestion,
    TaskRule,
    TaskStep,
    TaskUnderstanding,
)


class TaskUnderstandingStore:
    def __init__(self) -> None:
        self._records: dict[str, TaskUnderstanding] = {}

    def _key(self, tenant_id: str, workflow_id: str) -> str:
        return f"{tenant_id}:{workflow_id}"

    def _touch(self, task: TaskUnderstanding) -> None:
        task.updated_at = datetime.now(UTC)

    def create_or_get(self, tenant_id: str, workflow_id: str, task_name: str) -> TaskUnderstanding:
        key = self._key(tenant_id=tenant_id, workflow_id=workflow_id)
        existing = self._records.get(key)
        if existing:
            return existing

        task = TaskUnderstanding(
            task_id=str(uuid4()),
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            task_name=task_name,
        )
        self._records[key] = task
        return task

    def get(self, tenant_id: str, workflow_id: str) -> Optional[TaskUnderstanding]:
        return self._records.get(self._key(tenant_id=tenant_id, workflow_id=workflow_id))

    def add_step(
        self,
        tenant_id: str,
        workflow_id: str,
        description: str,
        screen_hint: Optional[str] = None,
        expected_result: Optional[str] = None,
    ) -> TaskUnderstanding:
        task = self.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        task.steps.append(
            TaskStep(
                step_id=str(uuid4()),
                order=len(task.steps) + 1,
                description=description,
                screen_hint=screen_hint,
                expected_result=expected_result,
            )
        )
        self._touch(task)
        return task

    def add_rule(
        self,
        tenant_id: str,
        workflow_id: str,
        rule_text: str,
        confidence: float = 0.7,
    ) -> TaskUnderstanding:
        task = self.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        task.rules.append(
            TaskRule(
                rule_id=str(uuid4()),
                rule_text=rule_text,
                confidence=confidence,
            )
        )
        self._touch(task)
        return task

    def add_decision(
        self,
        tenant_id: str,
        workflow_id: str,
        question: str,
        condition: str,
        if_true: Optional[str] = None,
        if_false: Optional[str] = None,
    ) -> TaskUnderstanding:
        task = self.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        task.decisions.append(
            TaskDecision(
                decision_id=str(uuid4()),
                question=question,
                condition=condition,
                if_true=if_true,
                if_false=if_false,
            )
        )
        self._touch(task)
        return task

    def add_edge_case(
        self,
        tenant_id: str,
        workflow_id: str,
        situation: str,
        expected_response: str,
        confidence: float = 0.7,
    ) -> TaskUnderstanding:
        task = self.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        task.edge_cases.append(
            TaskEdgeCase(
                edge_case_id=str(uuid4()),
                situation=situation,
                expected_response=expected_response,
                confidence=confidence,
            )
        )
        self._touch(task)
        return task

    def add_open_question(
        self,
        tenant_id: str,
        workflow_id: str,
        question: str,
        reason: str,
        priority: str = "medium",
    ) -> TaskUnderstanding:
        task = self.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        task.open_questions.append(
            TaskOpenQuestion(
                question_id=str(uuid4()),
                question=question,
                reason=reason,
                priority=priority,
            )
        )
        self._touch(task)
        return task

    def answer_open_question(
        self,
        tenant_id: str,
        workflow_id: str,
        question_id: str,
        answer: str,
    ) -> TaskUnderstanding:
        task = self.create_or_get(tenant_id=tenant_id, workflow_id=workflow_id, task_name=workflow_id)
        for question in task.open_questions:
            if question.question_id == question_id:
                question.answered = True
                question.answer = answer
                self._touch(task)
                break
        return task

    def list_by_tenant(self, tenant_id: str) -> list[TaskUnderstanding]:
        return [task for task in self._records.values() if task.tenant_id == tenant_id]


task_understanding_store = TaskUnderstandingStore()