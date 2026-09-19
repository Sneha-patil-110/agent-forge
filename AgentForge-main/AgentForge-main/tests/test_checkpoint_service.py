from __future__ import annotations

import logging
from pathlib import Path

import pytest
from langgraph.checkpoint.sqlite import SqliteSaver

from backend.services.checkpoint_service import CheckpointService, _collect_state_classes
from backend.state.workflow_state import WorkflowState
from backend.utils.run_id import generate_run_id


@pytest.fixture
def checkpoint_service(tmp_path: Path) -> CheckpointService:
    return CheckpointService(runs_root=tmp_path / "runs")


def test_checkpointer_for_run_creates_sqlite_file(
    checkpoint_service: CheckpointService, tmp_path: Path
) -> None:
    run_id = generate_run_id()

    checkpoint_service.checkpointer_for_run(run_id)

    db_path = tmp_path / "runs" / run_id / "checkpoints.sqlite"
    assert db_path.exists()


def test_checkpointer_for_run_returns_sqlite_saver(
    checkpoint_service: CheckpointService,
) -> None:
    saver = checkpoint_service.checkpointer_for_run(generate_run_id())

    assert isinstance(saver, SqliteSaver)


def test_checkpointer_for_run_rejects_invalid_run_id(
    checkpoint_service: CheckpointService,
) -> None:
    from backend.core.exceptions import InvalidRunIdError

    with pytest.raises(InvalidRunIdError):
        checkpoint_service.checkpointer_for_run("../../escape")


def test_collect_state_classes_covers_execution_state_fields() -> None:
    from backend.state.execution_state import ExecutionState, RepairTrigger, WorkflowStatus

    classes = _collect_state_classes(WorkflowState)

    assert ExecutionState in classes
    assert WorkflowStatus in classes
    assert RepairTrigger in classes


def _run_one_node(checkpoint_service: CheckpointService, run_id: str) -> None:
    from langgraph.graph import END, START, StateGraph

    def _node(state: WorkflowState) -> WorkflowState:
        state.execution.test_retry_count += 1
        return state

    graph = StateGraph(WorkflowState)
    graph.add_node("only", _node)
    graph.add_edge(START, "only")
    graph.add_edge("only", END)

    saver = checkpoint_service.checkpointer_for_run(run_id)
    compiled = graph.compile(checkpointer=saver)
    compiled.invoke(WorkflowState(), config={"configurable": {"thread_id": run_id}})
    saver.conn.close()


def test_sync_to_db_is_a_safe_no_op_without_a_session_factory(tmp_path: Path) -> None:
    service = CheckpointService(runs_root=tmp_path / "runs")
    run_id = generate_run_id()
    _run_one_node(service, run_id)

    service.sync_to_db(run_id)  # must not raise


def test_checkpoint_survives_local_disk_being_wiped(tmp_path: Path, db_session_factory) -> None:
    from backend.repositories.run_repository import RunRepository

    runs_root = tmp_path / "runs"
    service = CheckpointService(runs_root=runs_root, db_session_factory=db_session_factory)
    run_id = generate_run_id()

    _run_one_node(service, run_id)
    service.sync_to_db(run_id)

    with db_session_factory() as session:
        record = RunRepository(session).get(run_id)
        assert record is not None
        assert record.checkpoint_blob is not None
        assert len(record.checkpoint_blob) > 0

    db_path = runs_root / run_id / "checkpoints.sqlite"
    for path in runs_root.glob(f"{run_id}/checkpoints.sqlite*"):
        path.unlink()
    assert not db_path.exists()

    saver = service.checkpointer_for_run(run_id)
    assert db_path.exists()

    from langgraph.graph import END, START, StateGraph

    def _node(state: WorkflowState) -> WorkflowState:
        state.execution.test_retry_count += 1
        return state

    graph = StateGraph(WorkflowState)
    graph.add_node("only", _node)
    graph.add_edge(START, "only")
    graph.add_edge("only", END)
    compiled = graph.compile(checkpointer=saver)

    snapshot = compiled.get_state({"configurable": {"thread_id": run_id}})
    assert snapshot.values["execution"].test_retry_count == 1


def test_reopening_same_run_id_does_not_warn_about_unregistered_types(
    checkpoint_service: CheckpointService, caplog
) -> None:

    run_id = generate_run_id()

    from langgraph.graph import END, START, StateGraph

    def _node(state: WorkflowState) -> WorkflowState:
        state.execution.test_retry_count += 1
        return state

    graph = StateGraph(WorkflowState)
    graph.add_node("only", _node)
    graph.add_edge(START, "only")
    graph.add_edge("only", END)

    config = {"configurable": {"thread_id": run_id}}

    saver_a = checkpoint_service.checkpointer_for_run(run_id)
    compiled_a = graph.compile(checkpointer=saver_a)
    compiled_a.invoke(WorkflowState(), config=config)

    with caplog.at_level(logging.WARNING):
        saver_b = checkpoint_service.checkpointer_for_run(run_id)
        compiled_b = graph.compile(checkpointer=saver_b)
        compiled_b.invoke(WorkflowState(), config=config)

    unregistered_warnings = [
        r for r in caplog.records if "unregistered type" in r.message.lower()
    ]
    assert unregistered_warnings == []
