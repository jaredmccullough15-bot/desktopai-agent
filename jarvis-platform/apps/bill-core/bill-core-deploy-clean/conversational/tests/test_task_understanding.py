from conversational.task_understanding_service import TaskUnderstandingService
from conversational.task_understanding_store import TaskUnderstandingStore
from conversational.teaching_question_engine import TeachingQuestionEngine


def _service() -> TaskUnderstandingService:
    return TaskUnderstandingService(
        store=TaskUnderstandingStore(),
        question_engine=TeachingQuestionEngine(),
    )


def test_start_teaching_creates_task_understanding() -> None:
    service = _service()

    response = service.start_teaching(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        task_name="Smart Sherpa Sync",
    )

    assert response["task"]["tenant_id"] == "tenant-1"
    assert response["task"]["workflow_id"] == "smart_sherpa_sync"


def test_first_generated_question_asks_for_first_human_step() -> None:
    service = _service()

    response = service.start_teaching(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        task_name="Smart Sherpa Sync",
    )

    assert response["next_question"] is not None
    assert response["next_question"]["question"] == "What is the first thing a human does when starting this task?"


def test_recording_starting_note_adds_step() -> None:
    service = _service()
    service.start_teaching(tenant_id="tenant-1", workflow_id="smart_sherpa_sync", task_name="Smart Sherpa Sync")

    response = service.record_teaching_note(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        note="First I log into Health Sherpa and open the client list.",
    )

    assert len(response["task"]["steps"]) == 1


def test_recording_error_note_adds_edge_case() -> None:
    service = _service()
    service.start_teaching(tenant_id="tenant-1", workflow_id="smart_sherpa_sync", task_name="Smart Sherpa Sync")

    response = service.record_teaching_note(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        note="If login fails, I get stuck on the error page.",
    )

    assert len(response["task"]["edge_cases"]) == 1


def test_answering_open_question_marks_it_answered() -> None:
    service = _service()
    start = service.start_teaching(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        task_name="Smart Sherpa Sync",
    )
    question_id = start["next_question"]["question_id"]

    response = service.answer_question(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
        question_id=question_id,
        answer="The first step is opening Health Sherpa.",
    )

    answered = [q for q in response["task"]["open_questions"] if q["question_id"] == question_id][0]
    assert answered["answered"] is True
    assert answered["answer"] == "The first step is opening Health Sherpa."


def test_tenant_isolation_works() -> None:
    service = _service()

    service.start_teaching(tenant_id="tenant-1", workflow_id="smart_sherpa_sync", task_name="Tenant1 Task")
    service.start_teaching(tenant_id="tenant-2", workflow_id="smart_sherpa_sync", task_name="Tenant2 Task")

    tenant_1_tasks = service._store.list_by_tenant("tenant-1")
    tenant_2_tasks = service._store.list_by_tenant("tenant-2")

    assert len(tenant_1_tasks) == 1
    assert len(tenant_2_tasks) == 1
    assert tenant_1_tasks[0].tenant_id == "tenant-1"
    assert tenant_2_tasks[0].tenant_id == "tenant-2"