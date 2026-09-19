from __future__ import annotations

import json
from datetime import datetime

from langchain_core.messages import HumanMessage

from backend.state.architecture_state import ArchitectureState
from backend.state.conversation_state import ConversationState
from backend.state.documentation_state import DocumentationState
from backend.state.execution_state import AgentType, ExecutionState, WorkflowStatus
from backend.state.implementation_state import ImplementationState
from backend.state.planning_state import PlanningState
from backend.state.project_state import ProjectState, ProjectStatus
from backend.state.review_state import ReviewState
from backend.state.workflow_state import WorkflowState


ALL_STATE_MODELS = [
    ConversationState,
    ProjectState,
    PlanningState,
    ArchitectureState,
    ImplementationState,
    ReviewState,
    DocumentationState,
    ExecutionState,
    WorkflowState,
]


def test_every_state_model_constructs_with_defaults() -> None:
    for model in ALL_STATE_MODELS:
        instance = model()
        assert instance is not None


def test_every_state_model_round_trips_through_json() -> None:
    for model in ALL_STATE_MODELS:
        instance = model()
        dumped = instance.model_dump_json()
        restored = model.model_validate_json(dumped)
        assert restored == instance


def test_every_state_model_round_trips_through_dict() -> None:
    for model in ALL_STATE_MODELS:
        instance = model()
        dumped = instance.model_dump()
        restored = model.model_validate(dumped)
        assert restored.model_dump() == dumped


def test_project_status_enum_serializes_to_value() -> None:
    state = ProjectState(status=ProjectStatus.ANALYZED)

    data = json.loads(state.model_dump_json())

    assert data["status"] == "analyzed"


def test_execution_state_enum_fields_serialize_to_value() -> None:
    state = ExecutionState(
        workflow_status=WorkflowStatus.RUNNING,
        current_agent=AgentType.DEVELOPER,
    )

    data = json.loads(state.model_dump_json())

    assert data["workflow_status"] == "running"
    assert data["current_agent"] == "developer"


def test_project_state_datetime_fields_serialize_and_restore() -> None:
    state = ProjectState()

    dumped = state.model_dump_json()
    data = json.loads(dumped)

    assert isinstance(data["created_at"], str)
    assert isinstance(data["updated_at"], str)

    restored = ProjectState.model_validate_json(dumped)

    assert isinstance(restored.created_at, datetime)
    assert restored.created_at == state.created_at


def test_execution_state_completed_at_optional_datetime_round_trips() -> None:
    state = ExecutionState()

    assert state.completed_at is None

    dumped = state.model_dump_json()
    restored = ExecutionState.model_validate_json(dumped)

    assert restored.completed_at is None


def test_conversation_state_holds_langchain_messages() -> None:
    state = ConversationState(
        messages=[HumanMessage(content="Build a task manager.")]
    )

    assert state.messages[0].content == "Build a task manager."


def test_workflow_state_nests_every_sub_state() -> None:
    state = WorkflowState()

    assert isinstance(state.conversation, ConversationState)
    assert isinstance(state.project, ProjectState)
    assert isinstance(state.planning, PlanningState)
    assert isinstance(state.architecture, ArchitectureState)
    assert isinstance(state.implementation, ImplementationState)
    assert isinstance(state.review, ReviewState)
    assert isinstance(state.documentation, DocumentationState)
    assert isinstance(state.execution, ExecutionState)


def test_workflow_state_nested_validation_propagates() -> None:

    import pytest
    from pydantic import ValidationError

    payload = WorkflowState().model_dump()
    payload["planning"]["tasks"] = [
        {"id": "T1", "title": "a", "dependencies": ["T1"]},
    ]

    with pytest.raises(ValidationError):
        WorkflowState.model_validate(payload)


def test_analysis_output_schema_matches_project_state() -> None:
    payload = {
        "project_name": "Task Manager",
        "project_description": "A task tracking app.",
        "objective": "Let users manage tasks.",
        "requirements": ["Auth", "CRUD tasks"],
        "backend": "FastAPI",
        "frontend": "React",
        "database": "PostgreSQL",
        "deployment": "Docker",
        "target_audience": "Teams",
        "pending_clarifications": [],
        "tech_stack": ["FastAPI", "React", "PostgreSQL"],
        "output_directory": None,
        "status": "analyzed",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    state = ProjectState.model_validate(payload)

    assert state.project_name == "Task Manager"
    assert state.status == ProjectStatus.ANALYZED


def test_reviewer_output_schema_matches_review_state() -> None:
    payload = {
        "passed": True,
        "score": 8.5,
        "issues": [],
        "strengths": ["Clear separation of concerns."],
        "recommendations": ["Add integration tests."],
        "review_summary": "Implementation satisfies requirements.",
    }

    state = ReviewState.model_validate(payload)

    assert state.passed is True
    assert state.score == 8.5
