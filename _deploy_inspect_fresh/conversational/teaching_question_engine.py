from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from conversational.task_understanding_models import TaskOpenQuestion, TaskUnderstanding


class TeachingQuestionEngine:
    _priority_order = {"high": 0, "medium": 1, "low": 2}

    def next_question(self, task: TaskUnderstanding) -> Optional[TaskOpenQuestion]:
        unanswered = [question for question in task.open_questions if not question.answered]
        if unanswered:
            unanswered.sort(key=lambda q: self._priority_order.get(q.priority, 99))
            return unanswered[0]

        generated: TaskOpenQuestion | None = None
        if not task.steps:
            generated = TaskOpenQuestion(
                question_id=str(uuid4()),
                question="What is the first thing a human does when starting this task?",
                reason="Bill needs a starting point before this can become a repeatable workflow.",
                priority="high",
            )
        elif not task.decisions:
            generated = TaskOpenQuestion(
                question_id=str(uuid4()),
                question="What is the first decision point where the human has to choose what to do next?",
                reason="Bill needs to understand branching logic, not just clicks.",
                priority="high",
            )
        elif not task.edge_cases:
            generated = TaskOpenQuestion(
                question_id=str(uuid4()),
                question="What is the most common thing that goes wrong during this task?",
                reason="Bill needs failure handling before this workflow can be trusted.",
                priority="medium",
            )

        if generated is None:
            return None

        task.open_questions.append(generated)
        task.updated_at = datetime.now(UTC)
        return generated


teaching_question_engine = TeachingQuestionEngine()