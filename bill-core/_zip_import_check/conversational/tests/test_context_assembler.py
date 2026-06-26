from conversational.context_assembler import ContextAssembler
from conversational.execution_tracker import execution_tracker
from conversational.memory_models import WorkingMemoryTurn
from conversational.memory_store import MemoryStore


def test_context_assembler_extracts_capitalized_entities() -> None:
    store = MemoryStore()
    assembler = ContextAssembler(store)

    entities = assembler.extract_entities("Review Rebecca in Texas for AcmePolicy")

    assert "Rebecca" in entities
    assert "Texas" in entities
    assert "AcmePolicy" in entities


def test_working_memory_records_turns() -> None:
    store = MemoryStore()
    assembler = ContextAssembler(store)

    store.add_turn(
        WorkingMemoryTurn(
            tenant_id="tenant-1",
            session_id="session-1",
            role="user",
            message="Hello Bill",
        )
    )
    store.add_turn(
        WorkingMemoryTurn(
            tenant_id="tenant-1",
            session_id="session-1",
            role="assistant",
            message="Hi. Routing only for now.",
        )
    )

    context = assembler.assemble("tenant-1", "session-1", "What do you remember")

    assert len(context.working_memory) == 2
    assert context.working_memory[0].role == "user"
    assert context.working_memory[1].role == "assistant"


def test_context_includes_recent_executions_for_smart_sherpa() -> None:
    execution_tracker.records.clear()
    store = MemoryStore()
    assembler = ContextAssembler(store)

    execution_tracker.log_execution(
        tenant_id="tenant-1",
        user_id="session-1",
        workflow_id="smart_sherpa_sync",
        task_id="task-1",
        confidence=0.9,
        context_snapshot={"entities": ["Acme"]},
        intent="run_workflow",
    )
    execution_tracker.mark_status(tenant_id="tenant-1", task_id="task-1", status="completed")

    context = assembler.assemble("tenant-1", "session-1", "Please run smart sherpa now")

    assert len(context.recent_executions) == 1
    assert context.recent_executions[0]["workflow_id"] == "smart_sherpa_sync"
    assert context.workflow_success_signal > 0.5
