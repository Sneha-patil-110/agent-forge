from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.core.exceptions import AgentValidationError
from backend.state.execution_state import RepairTrigger, WorkflowStatus
from backend.state.review_state import ReviewIssue, Severity
from backend.state.workflow_state import WorkflowState


class RecordingLLMService:

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def invoke(self, *, model_role, prompt, context, response_schema=None, extra_messages=None, **_):
        self.calls.append(
            {
                "model_role": model_role,
                "prompt": prompt,
                "context": context,
                "response_schema": response_schema,
                "extra_messages": extra_messages,
            }
        )
        return AIMessage(content=self.content)


class RecordingPromptService:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    def load(self, prompt_file: str) -> str:
        self.loaded.append(prompt_file)
        return f"SYSTEM PROMPT for {prompt_file}"


VALID_PROJECT_STATE = {
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

VALID_PLANNING_STATE = {
    "project_summary": "Task manager summary.",
    "implementation_strategy": "Layered architecture.",
    "tasks": [
        {
            "id": "T1",
            "title": "Setup",
            "description": "Scaffold the project.",
            "dependencies": [],
            "milestone": None,
            "is_completed": False,
        }
    ],
    "milestones": [],
    "assumptions": [],
    "risks": [],
    "dependencies": [],
}

VALID_ARCHITECTURE_STATE = {
    "architecture_summary": "Layered REST API.",
    "system_design": {
        "layers": [
            {
                "name": "API",
                "description": "Handles requests.",
                "components": ["Router"],
            }
        ],
        "communication_flow": "Client -> API -> Service -> DB",
    },
    "folder_structure": {"backend": {}},
    "api_design": {
        "style": "REST",
        "endpoints": [
            {"method": "GET", "path": "/tasks", "description": "List tasks."}
        ],
    },
    "components": [
        {
            "name": "TaskService",
            "description": "Handles task logic.",
            "responsibilities": ["Create tasks"],
            "dependencies": [],
        }
    ],
    "database_design": {
        "database_type": "PostgreSQL",
        "entities": ["Task"],
        "relationships": [],
    },
    "design_patterns": ["Repository"],
    "architecture_decisions": [
        {
            "id": "AD1",
            "title": "Layered architecture",
            "description": "Improves maintainability.",
            "status": "accepted",
        }
    ],
}

VALID_IMPLEMENTATION_STATE = {
    "generated_code": [
        {
            "path": "app.py",
            "content": "print('hello')\n",
            "language": "python",
            "description": "Entry point.",
        }
    ],
    "completed_tasks": ["T1"],
    "failed_tasks": [],
    "implementation_notes": "Implemented task T1.",
}

VALID_REVIEW_STATE = {
    "passed": True,
    "score": 8.0,
    "issues": [],
    "strengths": ["Clean code."],
    "recommendations": [],
    "review_summary": "Looks good.",
}

VALID_DOCUMENTATION_STATE = {
    "generated_docs": [
        {
            "title": "README",
            "path": "README.md",
            "content": "# Task Manager\n",
            "description": "Project overview.",
        }
    ],
    "documentation_summary": "Generated README.",
    "pending_documentation": [],
}


def _make_agent(agent_cls, content: str):
    prompt_service = RecordingPromptService()
    llm_service = RecordingLLMService(content)
    agent = agent_cls(prompt_service, llm_service)
    return agent, prompt_service, llm_service


@pytest.mark.parametrize(
    "agent_cls, prompt_file, model_role, payload, state_attr",
    [
        (AnalysisAgent, "analysis.md", "analysis", VALID_PROJECT_STATE, "project"),
        (PlannerAgent, "planner.md", "planner", VALID_PLANNING_STATE, "planning"),
        (ArchitectAgent, "architect.md", "architect", VALID_ARCHITECTURE_STATE, "architecture"),
        (DeveloperAgent, "developer.md", "developer", VALID_IMPLEMENTATION_STATE, "implementation"),
        (ReviewerAgent, "reviewer.md", "reviewer", VALID_REVIEW_STATE, "review"),
        (DocumentationAgent, "documentation.md", "documentation", VALID_DOCUMENTATION_STATE, "documentation"),
    ],
)
def test_agent_happy_path(
    agent_cls, prompt_file, model_role, payload, state_attr
) -> None:
    agent, prompt_service, llm_service = _make_agent(
        agent_cls, json.dumps(payload)
    )

    state = WorkflowState()
    result = agent.run(state)

    assert prompt_service.loaded == [prompt_file]
    assert llm_service.calls[0]["model_role"] == model_role
    assert llm_service.calls[0]["prompt"] == f"SYSTEM PROMPT for {prompt_file}"

    updated_sub_state = getattr(result, state_attr)
    assert updated_sub_state is not None

    assert result.execution.current_agent.value == agent.name
    assert result.execution.error_message is None


@pytest.mark.parametrize(
    "agent_cls",
    [
        AnalysisAgent,
        PlannerAgent,
        ArchitectAgent,
        DeveloperAgent,
        ReviewerAgent,
        DocumentationAgent,
    ],
)
def test_agent_invalid_json_raises_agent_validation_error(agent_cls) -> None:
    agent, _, _ = _make_agent(agent_cls, "not json at all")

    state = WorkflowState()

    with pytest.raises(AgentValidationError):
        agent.run(state)

    assert state.execution.workflow_status == WorkflowStatus.FAILED
    assert state.execution.error_message is not None


@pytest.mark.parametrize(
    "agent_cls, invalid_payload",
    [
        (AnalysisAgent, {"requirements": "not-a-list"}),
        (PlannerAgent, {"tasks": "not-a-list"}),
        (ArchitectAgent, {"components": "not-a-list"}),
        (DeveloperAgent, {"generated_code": "not-a-list"}),
        (ReviewerAgent, {"score": 999}),
        (DocumentationAgent, {"generated_docs": "not-a-list"}),
    ],
)
def test_agent_schema_mismatch_raises_agent_validation_error(
    agent_cls, invalid_payload
) -> None:
    agent, _, _ = _make_agent(agent_cls, json.dumps(invalid_payload))

    state = WorkflowState()

    with pytest.raises(AgentValidationError):
        agent.run(state)

    assert state.execution.workflow_status == WorkflowStatus.FAILED


def test_analysis_agent_context_includes_conversation_and_project_state() -> None:
    agent, _, llm_service = _make_agent(
        AnalysisAgent, json.dumps(VALID_PROJECT_STATE)
    )

    state = WorkflowState()
    state.conversation.summary = "User wants a task manager."

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Conversation History" in context
    assert "User wants a task manager." in context
    assert "Current Project State" in context


def test_developer_agent_context_includes_debug_and_review_feedback_on_review_repair() -> None:
    agent, _, llm_service = _make_agent(
        DeveloperAgent, json.dumps(VALID_IMPLEMENTATION_STATE)
    )

    state = WorkflowState()
    state.execution.last_repair_trigger = RepairTrigger.REVIEW_FEEDBACK
    state.review.passed = False
    state.review.review_summary = "Missing input validation."
    state.review.issues = [
        ReviewIssue(
            title="No validation",
            description="Endpoint accepts unvalidated input.",
            severity=Severity.HIGH,
            file_path="app.py",
            suggestion="Validate the request body.",
        )
    ]
    state.debug.failure_summary = "Review flagged missing input validation on app.py."
    state.debug.root_cause = "The endpoint does not validate the request body before use."
    state.debug.affected_files = ["app.py"]
    state.debug.repair_instructions = "Add request body validation to the endpoint."

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Review Feedback Evidence" in context
    assert "Missing input validation." in context
    assert "No validation" in context
    assert "Debug Feedback" in context
    assert "The endpoint does not validate the request body before use." in context


def test_developer_agent_context_includes_debug_feedback_on_test_repair() -> None:
    agent, _, llm_service = _make_agent(
        DeveloperAgent, json.dumps(VALID_IMPLEMENTATION_STATE)
    )

    state = WorkflowState()
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.debug.failure_summary = "test_divide_by_zero failed."
    state.debug.root_cause = "divide() does not validate the divisor."
    state.debug.affected_files = ["calc.py"]
    state.debug.repair_instructions = "Raise ValueError when dividing by zero."
    state.testing.command = ["python", "-m", "pytest"]
    state.testing.stderr = "ZeroDivisionError: division by zero"

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Debug Feedback" in context
    assert "divide() does not validate the divisor." in context
    assert "Failed Test Execution Evidence" in context
    assert "ZeroDivisionError" in context
    assert "Review Feedback" not in context


def test_developer_agent_context_omits_all_feedback_on_initial_run() -> None:
    agent, _, llm_service = _make_agent(
        DeveloperAgent, json.dumps(VALID_IMPLEMENTATION_STATE)
    )

    state = WorkflowState()

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Review Feedback" not in context
    assert "Debug Feedback" not in context


def test_agent_failure_updates_execution_state_and_does_not_swallow_exception() -> None:
    agent, _, _ = _make_agent(AnalysisAgent, "")

    state = WorkflowState()

    with pytest.raises(AgentValidationError) as exc_info:
        agent.run(state)

    assert state.execution.workflow_status == WorkflowStatus.FAILED
    assert state.execution.current_step == "Failed during analysis agent"
    assert "empty response" in str(exc_info.value).lower()


def test_analysis_agent_preserves_system_controlled_fields() -> None:
    payload = dict(VALID_PROJECT_STATE)
    payload["output_directory"] = "/should/be/ignored"
    payload["status"] = "completed"

    agent, _, _ = _make_agent(AnalysisAgent, json.dumps(payload))

    state = WorkflowState()
    state.project.output_directory = "/configured/workspace/project"

    result = agent.run(state)

    assert result.project.output_directory == "/configured/workspace/project"
