from conversational.confidence_engine import ConfidenceEngine, ConfidenceInput
from conversational.intent_router import intent_router


def test_confidence_score_stays_between_zero_and_one() -> None:
    engine = ConfidenceEngine()
    score = engine.score(
        ConfidenceInput(
            message="smart sherpa sync Acme",
            intent="run_workflow",
            workflow_id="smart_sherpa_sync",
            entity_count=3,
            working_memory_turns=5,
        )
    )
    assert 0.0 <= score <= 1.0


def test_smart_sherpa_message_routes_to_smart_sherpa_sync() -> None:
    routed = intent_router.route("Please run Health Sherpa for this tenant")
    assert routed.action == "run_workflow"
    assert routed.workflow_id == "smart_sherpa_sync"
