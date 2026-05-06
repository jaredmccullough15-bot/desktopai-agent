from pydantic import BaseModel


class ConfidenceInput(BaseModel):
    message: str
    intent: str
    workflow_id: str | None = None
    entity_count: int = 0
    working_memory_turns: int = 0
    historical_success_rate: float = 0.5


class ConfidenceEngine:
    def score(self, confidence_input: ConfidenceInput) -> float:
        score = 0.5

        if confidence_input.intent in {"run_workflow", "start_teach_session", "memory_query"}:
            score += 0.2

        if confidence_input.workflow_id:
            score += 0.1

        if confidence_input.entity_count > 0:
            score += 0.1

        if confidence_input.working_memory_turns >= 2:
            score += 0.05

        # Keep this influence intentionally slight so existing routing behavior remains stable.
        score += (confidence_input.historical_success_rate - 0.5) * 0.2

        if len((confidence_input.message or "").strip()) < 4:
            score -= 0.35

        return max(0.0, min(1.0, score))

    def should_execute(self, confidence_score: float) -> bool:
        return confidence_score >= 0.75

    def should_clarify(self, confidence_score: float) -> bool:
        return 0.45 <= confidence_score < 0.75

    def should_escalate(self, confidence_score: float) -> bool:
        return confidence_score < 0.45
