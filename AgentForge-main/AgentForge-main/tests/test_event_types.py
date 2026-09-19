from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.events.event_types import EventType, WorkflowEvent
from backend.state.execution_state import AgentType


def test_workflow_event_requires_event_type_and_run_id() -> None:
    event = WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id="af_20260714_deadbeef")

    assert event.event_type == EventType.WORKFLOW_STARTED
    assert event.run_id == "af_20260714_deadbeef"


def test_workflow_event_missing_run_id_raises() -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent(event_type=EventType.WORKFLOW_STARTED)


def test_workflow_event_missing_event_type_raises() -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent(run_id="af_20260714_deadbeef")


def test_workflow_event_rejects_invalid_event_type() -> None:
    with pytest.raises(ValidationError):
        WorkflowEvent(event_type="not_a_real_event", run_id="af_20260714_deadbeef")


def test_workflow_event_optional_fields_default_safely() -> None:
    event = WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id="af_20260714_deadbeef")

    assert event.agent is None
    assert event.message is None
    assert event.metadata == {}


def test_workflow_event_timestamp_auto_populated_and_recent() -> None:
    from datetime import UTC, datetime

    before = datetime.now(UTC)
    event = WorkflowEvent(event_type=EventType.WORKFLOW_STARTED, run_id="af_20260714_deadbeef")
    after = datetime.now(UTC)

    assert before <= event.timestamp <= after
    assert event.timestamp.tzinfo is not None


def test_workflow_event_accepts_agent_type() -> None:
    event = WorkflowEvent(
        event_type=EventType.AGENT_STARTED,
        run_id="af_20260714_deadbeef",
        agent=AgentType.ARCHITECT,
    )

    assert event.agent == AgentType.ARCHITECT


def test_workflow_event_metadata_is_a_plain_dict_not_full_state() -> None:
    event = WorkflowEvent(
        event_type=EventType.TESTING_FAILED,
        run_id="af_20260714_deadbeef",
        metadata={"attempt_number": 2},
    )

    assert event.metadata == {"attempt_number": 2}
    assert not hasattr(event, "workflow_state")
    assert not hasattr(event, "prompt")
    assert not hasattr(event, "generated_code")


def test_all_expected_lifecycle_event_types_exist() -> None:
    expected = {
        "workflow_started",
        "workflow_resumed",
        "agent_started",
        "agent_completed",
        "testing_passed",
        "testing_failed",
        "review_passed",
        "review_failed",
        "reviewer_attempt_started",
        "reviewer_attempt_completed",
        "reviewer_repair_requested",
        "reviewer_auto_passed",
        "workflow_completed",
        "workflow_completed_with_verification_issues",
        "workflow_interrupted",
        "workflow_failed",
        "mcp_tool_call_started",
        "mcp_tool_call_completed",
        "mcp_tool_call_failed",
        "mcp_tool_call_recorded",
        "file_created",
        "file_modified",
        "file_deleted",
        "file_renamed",
        "folder_created",
        "folder_deleted",
        "documentation_generated",
        "agent_invocation_recorded",
        "recovery_action_taken",
        "repository_materialized",
        "repository_integrity_started",
        "repository_integrity_passed",
        "repository_integrity_failed",
        "repository_snapshot_created",
        "tester_context_created",
    }

    assert {member.value for member in EventType} == expected



def test_workflow_event_round_trips_through_json() -> None:
    event = WorkflowEvent(
        event_type=EventType.REVIEW_PASSED,
        run_id="af_20260714_deadbeef",
        agent=AgentType.REVIEWER,
        message="Review passed",
        metadata={"score": 8.5},
    )

    restored = WorkflowEvent.model_validate_json(event.model_dump_json())

    assert restored == event
