
from __future__ import annotations

from pathlib import Path

import pytest

from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.graph.workflow import WorkflowNode
from backend.services.checkpoint_service import CheckpointService
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import AgentType, WorkflowStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry
from backend.utils.run_id import generate_run_id

from tests.test_review_retry_integration import (
    REVIEW_PASSED,
    TEST_PLAN,
    VALID_ARCHITECTURE_STATE,
    VALID_DOCUMENTATION_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    WORKING_CALC_CONTENT,
    ScriptedLLMService,
    StubPromptService,
    _calc_file,
    _implementation_payload,
    _initial_state,
    _test_file,
)


def _build_nodes(output_directory: Path) -> WorkflowNodes:
    from backend.agents.analysis_agent import AnalysisAgent
    from backend.agents.architect_agent import ArchitectAgent
    from backend.agents.debugger_agent import DebuggerAgent
    from backend.agents.developer_agent import DeveloperAgent
    from backend.agents.documenter_agent import DocumentationAgent
    from backend.agents.planner_agent import PlannerAgent
    from backend.agents.reviewer_agent import ReviewerAgent
    from backend.agents.tester_agent import TesterAgent

    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [
                _implementation_payload(
                    _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                    _test_file(),
                )
            ],
            "tester": [TEST_PLAN],
            "debugger": [],
            "reviewer": [REVIEW_PASSED],
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    return WorkflowNodes(
        analysis_agent=AnalysisAgent(prompt_service, llm_service),
        planner_agent=PlannerAgent(prompt_service, llm_service),
        architect_agent=ArchitectAgent(prompt_service, llm_service),
        developer_agent=DeveloperAgent(prompt_service, llm_service),
        tester_agent=TesterAgent(prompt_service, llm_service),
        debugger_agent=DebuggerAgent(prompt_service, llm_service),
        reviewer_agent=ReviewerAgent(prompt_service, llm_service),
        documentation_agent=DocumentationAgent(prompt_service, llm_service),
        materialization_service=MaterializationService(tool_registry),
        testing_service=TestingService(tool_registry),
    )


def test_resume_does_not_reemit_events_for_already_completed_agents(
    tmp_path: Path,
) -> None:
    run_id = generate_run_id()
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")
    config = {"configurable": {"thread_id": run_id}}

    dispatcher_a = EventDispatcher()
    events_a: list[WorkflowEvent] = []
    dispatcher_a.subscribe(events_a.append)

    checkpointer_a = checkpoint_service.checkpointer_for_run(run_id)
    graph_a = WorkflowBuilder(_build_nodes(output_directory)).build(
        checkpointer=checkpointer_a,
        event_dispatcher=dispatcher_a,
        run_id=run_id,
        interrupt_after=[WorkflowNode.ARCHITECT.value],
    )

    graph_a.invoke(_initial_state(output_directory), config=config)

    agents_started_in_a = {e.agent for e in events_a if e.event_type == EventType.AGENT_STARTED}
    assert agents_started_in_a == {AgentType.ANALYSIS, AgentType.PLANNER, AgentType.ARCHITECT}

    dispatcher_b = EventDispatcher()
    events_b: list[WorkflowEvent] = []
    dispatcher_b.subscribe(events_b.append)

    checkpointer_b = checkpoint_service.checkpointer_for_run(run_id)
    graph_b = WorkflowBuilder(_build_nodes(output_directory)).build(
        checkpointer=checkpointer_b,
        event_dispatcher=dispatcher_b,
        run_id=run_id,
    )

    result = graph_b.invoke(None, config=config)
    final_state = WorkflowState.model_validate(result)

    agents_started_in_b = {e.agent for e in events_b if e.event_type == EventType.AGENT_STARTED}

    assert agents_started_in_b == {
        AgentType.DEVELOPER,
        AgentType.STATIC_VALIDATION,
        AgentType.TESTER,
        AgentType.REVIEWER,
        AgentType.DOCUMENTATION,
    }
    assert AgentType.ANALYSIS not in agents_started_in_b
    assert AgentType.PLANNER not in agents_started_in_b
    assert AgentType.ARCHITECT not in agents_started_in_b

    for agent in (
        AgentType.DEVELOPER,
        AgentType.STATIC_VALIDATION,
        AgentType.TESTER,
        AgentType.REVIEWER,
        AgentType.DOCUMENTATION,
    ):
        started = [e for e in events_b if e.agent == agent and e.event_type == EventType.AGENT_STARTED]
        completed = [e for e in events_b if e.agent == agent and e.event_type == EventType.AGENT_COMPLETED]
        assert len(started) == 1
        assert len(completed) == 1

    assert final_state.execution.workflow_status == WorkflowStatus.COMPLETED


def test_resume_of_already_completed_workflow_does_not_rerun_or_reemit(
    tmp_path: Path,
) -> None:

    run_id = generate_run_id()
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")
    config = {"configurable": {"thread_id": run_id}}

    dispatcher_1 = EventDispatcher()
    events_1: list[WorkflowEvent] = []
    dispatcher_1.subscribe(events_1.append)

    checkpointer_1 = checkpoint_service.checkpointer_for_run(run_id)
    graph_1 = WorkflowBuilder(_build_nodes(output_directory)).build(
        checkpointer=checkpointer_1,
        event_dispatcher=dispatcher_1,
        run_id=run_id,
    )

    result = graph_1.invoke(_initial_state(output_directory), config=config)
    assert WorkflowState.model_validate(result).execution.workflow_status == WorkflowStatus.COMPLETED
    assert len(events_1) > 0

    dispatcher_2 = EventDispatcher()
    events_2: list[WorkflowEvent] = []
    dispatcher_2.subscribe(events_2.append)

    checkpointer_2 = checkpoint_service.checkpointer_for_run(run_id)
    graph_2 = WorkflowBuilder(_build_nodes(output_directory)).build(
        checkpointer=checkpointer_2,
        event_dispatcher=dispatcher_2,
        run_id=run_id,
    )

    graph_2.invoke(None, config=config)

    assert events_2 == []
