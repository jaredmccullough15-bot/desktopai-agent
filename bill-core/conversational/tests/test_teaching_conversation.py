from conversational.execution_tracker import execution_tracker
from conversational.task_understanding_service import TaskUnderstandingService
from conversational.task_understanding_store import TaskUnderstandingStore
from conversational.teaching_conversation_models import TeachingChatRequest
from conversational.teaching_conversation_service import TeachingConversationService
from conversational.teaching_conversation_store import TeachingConversationStore
from conversational.teaching_question_engine import TeachingQuestionEngine


def _service() -> TeachingConversationService:
    store = TaskUnderstandingStore()
    return TeachingConversationService(
        task_service=TaskUnderstandingService(store=store, question_engine=TeachingQuestionEngine()),
        task_store=store,
        question_engine=TeachingQuestionEngine(),
        conversation_store=TeachingConversationStore(),
    )


def test_chat_creates_teaching_conversation_state() -> None:
    service = _service()

    response = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="First I log into Health Sherpa.",
        )
    )

    assert response.conversation_state.session_id == "teach-session-1"
    assert response.conversation_state.turn_count == 1


def test_first_teaching_message_records_step() -> None:
    service = _service()

    response = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="First I log into Health Sherpa and open the client list.",
        )
    )

    assert len(response.task["steps"]) == 1


def test_bill_returns_next_relevant_question() -> None:
    service = _service()

    response = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="First I log into Health Sherpa.",
        )
    )

    assert response.next_question is not None
    assert "decision point" in response.next_question["question"].lower()


def test_answering_previous_question_marks_it_answered() -> None:
    service = _service()
    first = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="First I log into Health Sherpa.",
        )
    )
    question_id = first.conversation_state.last_question_id
    assert question_id is not None

    second = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="If the client is missing, I stop and verify account details.",
        )
    )

    answered = [q for q in second.task["open_questions"] if q["question_id"] == question_id][0]
    assert answered["answered"] is True


def test_conversation_state_increments_turn_count() -> None:
    service = _service()

    first = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="First I log into Health Sherpa.",
        )
    )
    second = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="If there is a mismatch, I escalate to support.",
        )
    )

    assert first.conversation_state.turn_count == 1
    assert second.conversation_state.turn_count == 2


def test_chat_does_not_execute_workflows() -> None:
    execution_tracker.records.clear()
    service = _service()

    _ = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-1",
            workflow_id="smart_sherpa_sync",
            task_name="Smart Sherpa Sync",
            session_id="teach-session-1",
            message="First I log into Health Sherpa.",
        )
    )

    assert len(execution_tracker.records) == 0


def test_tenant_session_isolation_works() -> None:
    service = _service()

    a = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-a",
            workflow_id="smart_sherpa_sync",
            task_name="Task A",
            session_id="session-a",
            message="First I do A.",
        )
    )
    b = service.chat(
        TeachingChatRequest(
            tenant_id="tenant-b",
            workflow_id="smart_sherpa_sync",
            task_name="Task B",
            session_id="session-b",
            message="First I do B.",
        )
    )

    assert a.conversation_state.tenant_id == "tenant-a"
    assert b.conversation_state.tenant_id == "tenant-b"
    assert a.task["tenant_id"] == "tenant-a"
    assert b.task["tenant_id"] == "tenant-b"