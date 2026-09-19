
from __future__ import annotations

from contextlib import contextmanager

import pytest

from backend.graph.builder import WorkflowBuilder
from backend.state.execution_state import RepairTrigger
from backend.state.workflow_state import WorkflowState


class _FakeTracingService:
    def __init__(self) -> None:
        self.spans: list[dict] = []

    @contextmanager
    def trace(self, name, *, run_type="chain", tags=None, metadata=None, inputs=None):
        entry = {"name": name, "run_type": run_type, "tags": tags, "metadata": metadata}
        self.spans.append(entry)

        try:
            yield entry
        except BaseException as error:
            entry["error"] = repr(error)
            raise

    def set_outputs(self, run, outputs) -> None:
        if run is None:
            return

        run["outputs"] = outputs


def test_wrap_with_tracing_opens_a_span_named_after_the_node() -> None:
    tracing = _FakeTracingService()
    seen_states = []

    def fn(state: WorkflowState) -> WorkflowState:
        seen_states.append(state)
        state.execution.current_step = "did work"
        return state

    wrapped = WorkflowBuilder._wrap_with_tracing(name="analysis", fn=fn, tracing_service=tracing)
    state = WorkflowState()

    result = wrapped(state)

    assert seen_states == [state]
    assert result is state
    assert len(tracing.spans) == 1
    span = tracing.spans[0]
    assert span["name"] == "analysis"
    assert span["run_type"] == "chain"
    assert span["tags"] == ["agent:analysis"]
    assert span["outputs"]["current_step"] == "did work"
    assert span["outputs"]["duration_ms"] >= 0


def test_wrap_with_tracing_propagates_exceptions_and_records_them() -> None:
    tracing = _FakeTracingService()

    def fn(state: WorkflowState) -> WorkflowState:
        raise RuntimeError("developer blew up")

    wrapped = WorkflowBuilder._wrap_with_tracing(name="developer", fn=fn, tracing_service=tracing)

    with pytest.raises(RuntimeError, match="developer blew up"):
        wrapped(WorkflowState())

    assert "error" in tracing.spans[0]
    assert "outputs" not in tracing.spans[0]




def test_first_developer_run_is_not_labeled_as_a_repair() -> None:
    tracing = _FakeTracingService()
    wrapped = WorkflowBuilder._wrap_with_tracing(
        name="developer", fn=lambda state: state, tracing_service=tracing
    )

    wrapped(WorkflowState())

    span = tracing.spans[0]
    assert span["name"] == "developer"
    assert "retry_triggered_by" not in span["metadata"]


def test_developer_repair_after_test_failure_is_labeled_and_carries_retry_metadata() -> None:
    tracing = _FakeTracingService()
    wrapped = WorkflowBuilder._wrap_with_tracing(
        name="developer", fn=lambda state: state, tracing_service=tracing
    )

    state = WorkflowState()
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.execution.test_retry_count = 1

    wrapped(state)

    span = tracing.spans[0]
    assert span["name"] == "developer_repair"
    assert span["metadata"]["agent"] == "developer"
    assert span["metadata"]["stage"] == "developer_repair"
    assert span["metadata"]["retry_triggered_by"] == "test_failure"
    assert span["metadata"]["retry_number"] == 1
    assert span["metadata"]["previous_stage"] == "tester"
    assert span["metadata"]["next_stage"] == "tester"


def test_developer_repair_after_review_failure_is_labeled_and_carries_retry_metadata() -> None:
    tracing = _FakeTracingService()
    wrapped = WorkflowBuilder._wrap_with_tracing(
        name="developer", fn=lambda state: state, tracing_service=tracing
    )

    state = WorkflowState()
    state.execution.last_repair_trigger = RepairTrigger.REVIEW_FEEDBACK
    state.execution.review_retry_count = 2

    wrapped(state)

    span = tracing.spans[0]
    assert span["name"] == "developer_repair"
    assert span["metadata"]["retry_triggered_by"] == "review_feedback"
    assert span["metadata"]["retry_number"] == 2
    assert span["metadata"]["previous_stage"] == "reviewer"
    assert span["metadata"]["next_stage"] == "tester"


def test_tester_span_carries_attempt_number_from_existing_retry_count() -> None:
    tracing = _FakeTracingService()
    wrapped = WorkflowBuilder._wrap_with_tracing(
        name="tester", fn=lambda state: state, tracing_service=tracing
    )

    state = WorkflowState()
    state.execution.test_retry_count = 1

    wrapped(state)

    span = tracing.spans[0]
    assert span["name"] == "tester"
    assert span["metadata"]["attempt_number"] == 2
    assert span["metadata"]["next_stage"] == "reviewer"


def test_reviewer_span_carries_attempt_number_from_existing_retry_count() -> None:
    tracing = _FakeTracingService()
    wrapped = WorkflowBuilder._wrap_with_tracing(
        name="reviewer", fn=lambda state: state, tracing_service=tracing
    )

    state = WorkflowState()
    state.execution.review_retry_count = 1

    wrapped(state)

    span = tracing.spans[0]
    assert span["metadata"]["attempt_number"] == 2
    assert span["metadata"]["next_stage"] == "documentation"


def test_debugger_span_is_labeled_as_test_failure_driven() -> None:
    tracing = _FakeTracingService()
    wrapped = WorkflowBuilder._wrap_with_tracing(
        name="debugger", fn=lambda state: state, tracing_service=tracing
    )

    wrapped(WorkflowState())

    span = tracing.spans[0]
    assert span["metadata"]["retry_triggered_by"] == "test_failure"
    assert span["metadata"]["previous_stage"] == "tester"
    assert span["metadata"]["next_stage"] == "developer"


def test_build_without_tracing_service_compiles_unchanged() -> None:

    from backend.graph.nodes import WorkflowNodes

    class _NoopAgent:
        def run(self, state):
            return state

    nodes = WorkflowNodes(
        analysis_agent=_NoopAgent(),
        planner_agent=_NoopAgent(),
        architect_agent=_NoopAgent(),
        developer_agent=_NoopAgent(),
        tester_agent=_NoopAgent(),
        debugger_agent=_NoopAgent(),
        reviewer_agent=_NoopAgent(),
        documentation_agent=_NoopAgent(),
        materialization_service=None,
        testing_service=None,
    )

    graph = WorkflowBuilder(nodes).build()

    assert graph is not None