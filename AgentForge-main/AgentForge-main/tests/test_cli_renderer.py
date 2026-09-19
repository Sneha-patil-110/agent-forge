from __future__ import annotations

import io

from backend.cli.renderer import CLIEventRenderer
from backend.events.event_types import EventType, WorkflowEvent
from backend.state.execution_state import AgentType

RUN_ID = "af_20260714_deadbeef"


def _render(event: WorkflowEvent) -> str:
    stream = io.StringIO()
    CLIEventRenderer(stream=stream)(event)
    return stream.getvalue().strip()


def test_renders_workflow_started() -> None:
    assert _render(WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id=RUN_ID)) == (
        "Workflow started"
    )


def test_renders_agent_started_with_agent_name() -> None:
    text = _render(
        WorkflowEvent(
            event_type=EventType.AGENT_STARTED, run_id=RUN_ID, agent=AgentType.ARCHITECT
        )
    )
    assert text == "Architect started"


def test_renders_agent_completed_with_agent_name() -> None:
    text = _render(
        WorkflowEvent(
            event_type=EventType.AGENT_COMPLETED, run_id=RUN_ID, agent=AgentType.ARCHITECT
        )
    )
    assert text == "Architect completed"


def test_renders_testing_passed_and_failed() -> None:
    assert _render(WorkflowEvent(event_type=EventType.TESTING_PASSED, run_id=RUN_ID)) == (
        "Testing passed"
    )
    assert _render(WorkflowEvent(event_type=EventType.TESTING_FAILED, run_id=RUN_ID)) == (
        "Testing failed"
    )


def test_renders_review_passed_and_failed() -> None:
    assert _render(WorkflowEvent(event_type=EventType.REVIEW_PASSED, run_id=RUN_ID)) == (
        "Review passed"
    )
    assert _render(WorkflowEvent(event_type=EventType.REVIEW_FAILED, run_id=RUN_ID)) == (
        "Review failed"
    )


def test_renders_workflow_interrupted() -> None:
    assert _render(WorkflowEvent(event_type=EventType.WORKFLOW_INTERRUPTED, run_id=RUN_ID)) == (
        "Workflow interrupted"
    )


def test_renders_workflow_completed() -> None:
    assert _render(WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id=RUN_ID)) == (
        "Workflow completed"
    )


def test_renders_workflow_failed_with_message() -> None:
    text = _render(
        WorkflowEvent(
            event_type=EventType.WORKFLOW_FAILED,
            run_id=RUN_ID,
            message="Testing failed after the maximum number of retries (3).",
        )
    )
    assert text == "Workflow failed: Testing failed after the maximum number of retries (3)."


def test_renders_workflow_resumed() -> None:
    assert _render(WorkflowEvent(event_type=EventType.WORKFLOW_RESUMED, run_id=RUN_ID)) == (
        "Workflow resumed"
    )


def test_renderer_output_contains_no_metadata_dump() -> None:
    text = _render(
        WorkflowEvent(
            event_type=EventType.TESTING_FAILED,
            run_id=RUN_ID,
            agent=AgentType.TESTER,
            metadata={"attempt_number": 2, "secret_marker": "should_not_leak_verbatim"},
        )
    )
    assert "secret_marker" not in text
    assert "should_not_leak_verbatim" not in text
