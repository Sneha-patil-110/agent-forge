from __future__ import annotations

import json

from backend.agents.architect_agent import ArchitectAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.graph.nodes import WorkflowNodes
from backend.services.knowledge_manager import KnowledgeManager
from backend.state.knowledge_state import KnowledgeCategory
from backend.state.planning_state import Task
from backend.state.testing_state import TestFailure, TestingState, TestStatus
from backend.state.workflow_state import WorkflowState

from tests.support.workflow_node_fixtures import (
    StubDependencyPreparationService,
    StubEnvironmentPreflightService,
    StubRepositoryIntegrityValidator,
    StubTestDiscoveryService,
)
from tests.test_agents import (
    VALID_ARCHITECTURE_STATE,
    VALID_IMPLEMENTATION_STATE,
    VALID_REVIEW_STATE,
    RecordingLLMService,
    RecordingPromptService,
)


def _make_agent(agent_cls, content: str, *, knowledge_manager: KnowledgeManager | None = None):
    prompt_service = RecordingPromptService()
    llm_service = RecordingLLMService(content)
    agent = agent_cls(prompt_service, llm_service, knowledge_manager=knowledge_manager)
    return agent




def test_architect_records_only_accepted_decisions() -> None:
    knowledge_manager = KnowledgeManager()
    payload = dict(VALID_ARCHITECTURE_STATE)
    payload["architecture_decisions"] = [
        {
            "id": "AD1",
            "title": "Repository Pattern",
            "description": "Use the repository pattern for data access.",
            "status": "accepted",
        },
        {
            "id": "AD2",
            "title": "Rejected idea",
            "description": "Considered and rejected.",
            "status": "rejected",
        },
    ]
    agent = _make_agent(ArchitectAgent, json.dumps(payload), knowledge_manager=knowledge_manager)
    state = WorkflowState()

    agent.run(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.ARCHITECTURE_DECISION])
    assert [e.title for e in entries] == ["Repository Pattern"]
    assert entries[0].source_id == "AD1"


def test_architect_does_not_duplicate_the_same_decision_across_runs() -> None:
    knowledge_manager = KnowledgeManager()
    payload = dict(VALID_ARCHITECTURE_STATE)
    payload["architecture_decisions"] = [
        {"id": "AD1", "title": "Repository Pattern", "description": "desc", "status": "accepted"}
    ]
    agent = _make_agent(ArchitectAgent, json.dumps(payload), knowledge_manager=knowledge_manager)
    state = WorkflowState()

    agent.run(state)
    agent.run(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.ARCHITECTURE_DECISION])
    assert len(entries) == 1




def test_developer_records_milestones_only_for_newly_completed_tasks() -> None:
    knowledge_manager = KnowledgeManager()
    payload = dict(VALID_IMPLEMENTATION_STATE)
    payload["completed_tasks"] = ["T1", "T2"]
    agent = _make_agent(DeveloperAgent, json.dumps(payload), knowledge_manager=knowledge_manager)

    state = WorkflowState()
    state.planning.tasks = [
        Task(id="T1", title="Scaffold project"),
        Task(id="T2", title="Add authentication"),
    ]
    state.implementation.completed_tasks = ["T1"]

    agent.run(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.COMPLETED_MILESTONE])
    assert [e.title for e in entries] == ["Add authentication"]
    assert entries[0].source_id == "T2"


def test_developer_records_nothing_when_no_new_tasks_completed() -> None:
    knowledge_manager = KnowledgeManager()
    payload = dict(VALID_IMPLEMENTATION_STATE)
    payload["completed_tasks"] = ["T1"]
    agent = _make_agent(DeveloperAgent, json.dumps(payload), knowledge_manager=knowledge_manager)

    state = WorkflowState()
    state.implementation.completed_tasks = ["T1"]

    agent.run(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.COMPLETED_MILESTONE])
    assert entries == []




def test_reviewer_records_recommendations_as_coding_standard_knowledge() -> None:
    knowledge_manager = KnowledgeManager()
    payload = dict(VALID_REVIEW_STATE)
    payload["recommendations"] = ["Use consistent naming for service classes."]
    agent = _make_agent(ReviewerAgent, json.dumps(payload), knowledge_manager=knowledge_manager)
    state = WorkflowState()

    agent.run(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.CODING_STANDARD])
    assert [e.content for e in entries] == ["Use consistent naming for service classes."]


def test_reviewer_does_not_duplicate_the_same_recommendation_across_review_cycles() -> None:
    knowledge_manager = KnowledgeManager()
    payload = dict(VALID_REVIEW_STATE)
    payload["recommendations"] = ["Use consistent naming for service classes."]
    agent = _make_agent(ReviewerAgent, json.dumps(payload), knowledge_manager=knowledge_manager)
    state = WorkflowState()

    agent.run(state)
    agent.run(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.CODING_STANDARD])
    assert len(entries) == 1




class _NoopTesterAgent:
    name = "tester"

    def run(self, state: WorkflowState) -> WorkflowState:
        return state


class _FailingTestingService:
    def execute_stage(self, *, project, plan, stage, attempt_number, targeted_tests=None) -> TestingState:
        return TestingState(
            status=TestStatus.FAILED,
            command=stage.command,
            passed=False,
            attempt_number=attempt_number,
            failed_tests=[
                TestFailure(name="test_divide_by_zero", message="ZeroDivisionError: division by zero")
            ],
        )


def test_workflow_nodes_tester_records_known_limitations_from_real_failures() -> None:
    knowledge_manager = KnowledgeManager()
    nodes = WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=_NoopTesterAgent(),
        debugger_agent=None,
        reviewer_agent=None,
        documentation_agent=None,
        materialization_service=None,
        testing_service=_FailingTestingService(),
        knowledge_manager=knowledge_manager,
        repository_integrity_validator=StubRepositoryIntegrityValidator(),
        test_discovery_service=StubTestDiscoveryService(),
        environment_preflight_service=StubEnvironmentPreflightService(),
        dependency_preparation_service=StubDependencyPreparationService(),
    )
    state = WorkflowState()

    nodes.tester(state)

    entries = knowledge_manager.get(state, categories=[KnowledgeCategory.KNOWN_LIMITATION])
    assert [e.title for e in entries] == ["test_divide_by_zero"]
    assert "ZeroDivisionError" in entries[0].content


def test_workflow_nodes_tester_records_nothing_when_tests_pass() -> None:
    class _PassingTestingService:
        def execute(self, *, project, command, attempt_number) -> TestingState:
            return TestingState(
                status=TestStatus.PASSED, command=command, passed=True, attempt_number=attempt_number
            )

    knowledge_manager = KnowledgeManager()
    nodes = WorkflowNodes(
        analysis_agent=None,
        planner_agent=None,
        architect_agent=None,
        developer_agent=None,
        tester_agent=_NoopTesterAgent(),
        debugger_agent=None,
        reviewer_agent=None,
        documentation_agent=None,
        materialization_service=None,
        testing_service=_PassingTestingService(),
        knowledge_manager=knowledge_manager,
    )
    state = WorkflowState()

    nodes.tester(state)

    assert knowledge_manager.get(state, categories=[KnowledgeCategory.KNOWN_LIMITATION]) == []