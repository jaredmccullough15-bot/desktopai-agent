from conversational.execution_tracker import execution_tracker


def test_no_execution_history_returns_neutral_signal() -> None:
    execution_tracker.records.clear()

    signal = execution_tracker.get_workflow_success_signal(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert signal == 0.5


def test_completed_executions_raise_signal() -> None:
    execution_tracker.records.clear()

    execution_tracker.log_execution(
        tenant_id="tenant-1",
        user_id="user-1",
        workflow_id="smart_sherpa_sync",
        task_id="task-1",
        confidence=0.9,
        context_snapshot={},
        intent="run_workflow",
    )
    execution_tracker.mark_status(tenant_id="tenant-1", task_id="task-1", status="completed")

    signal = execution_tracker.get_workflow_success_signal(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert signal > 0.5


def test_failed_executions_lower_signal() -> None:
    execution_tracker.records.clear()

    execution_tracker.log_execution(
        tenant_id="tenant-1",
        user_id="user-1",
        workflow_id="smart_sherpa_sync",
        task_id="task-2",
        confidence=0.9,
        context_snapshot={},
        intent="run_workflow",
    )
    execution_tracker.mark_status(tenant_id="tenant-1", task_id="task-2", status="failed")

    signal = execution_tracker.get_workflow_success_signal(
        tenant_id="tenant-1",
        workflow_id="smart_sherpa_sync",
    )

    assert signal < 0.5