
from __future__ import annotations

from pathlib import Path

from backend.agents.analysis_agent import AnalysisAgent
from backend.agents.architect_agent import ArchitectAgent
from backend.agents.debugger_agent import DebuggerAgent
from backend.agents.developer_agent import DeveloperAgent
from backend.agents.documenter_agent import DocumentationAgent
from backend.agents.planner_agent import PlannerAgent
from backend.agents.reviewer_agent import ReviewerAgent
from backend.agents.tester_agent import TesterAgent
from backend.core.constants import MAX_TEST_RETRIES
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.services.checkpoint_service import CheckpointService
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import RepairTrigger, WorkflowStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry
from backend.utils.run_id import generate_run_id

from tests.test_review_retry_integration import (
    BROKEN_CALC_CONTENT,
    DEBUG_ANALYSIS,
    REVIEW_PASSED,
    TESTER_ANALYSIS,
    VALID_ARCHITECTURE_STATE,
    VALID_DOCUMENTATION_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    WORKING_CALC_CONTENT,
    ScriptedLLMService,
    StubPromptService,
    _as_workflow_state,
    _calc_file,
    _implementation_payload,
    _initial_state,
    _test_file,
)


def _build_graph_and_nodes(output_directory: Path, checkpointer):
    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [
                _implementation_payload(
                    _calc_file(
                        BROKEN_CALC_CONTENT + f"\n# attempt {attempt}\n",
                        "Calculator module (buggy).",
                    ),
                    _test_file(),
                )
                for attempt in range(MAX_TEST_RETRIES + 1)
            ],
            "tester": [TESTER_ANALYSIS],
            "debugger": [DEBUG_ANALYSIS],
            "reviewer": [REVIEW_PASSED],
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    nodes = WorkflowNodes(
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

    graph = WorkflowBuilder(nodes).build(checkpointer=checkpointer)

    return graph, llm_service


def test_restart_from_checkpoint_recovers_a_retry_exhausted_run(tmp_path: Path) -> None:
    run_id = generate_run_id()
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")
    checkpointer = checkpoint_service.checkpointer_for_run(run_id)
    config = {"configurable": {"thread_id": run_id}}

    graph, llm_service = _build_graph_and_nodes(output_directory, checkpointer)

    result = _as_workflow_state(
        graph.invoke(_initial_state(output_directory), config={**config, "recursion_limit": 100})
    )

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert result.execution.test_retry_count == MAX_TEST_RETRIES + 1
    developer_calls_before_recovery = llm_service.call_count("developer")
    assert developer_calls_before_recovery == MAX_TEST_RETRIES + 1

    checkpoints = checkpoint_service.list_checkpoints(run_id)
    assert len(checkpoints) > 1

    latest_checkpoint_id = checkpoints[0].checkpoint_id
    target_config = {
        "configurable": {
            "thread_id": run_id,
            "checkpoint_ns": "",
            "checkpoint_id": latest_checkpoint_id,
        }
    }

    snapshot = graph.get_state(target_config)
    assert snapshot.values

    checkpointed_state = WorkflowState.model_validate(snapshot.values)
    assert checkpointed_state.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert checkpointed_state.execution.current_agent is not None
    as_node = checkpointed_state.execution.current_agent.value

    execution = checkpointed_state.execution
    execution.workflow_status = WorkflowStatus.RUNNING
    execution.error_message = None
    execution.test_retry_count = 0
    execution.review_retry_count = 0
    execution.last_repair_trigger = RepairTrigger.NONE

    graph.update_state(target_config, {"execution": execution}, as_node=as_node)

    llm_service._scripts["developer"] = [
        _implementation_payload(_calc_file(WORKING_CALC_CONTENT, "Calculator module (fixed)."))
    ]

    resumed_result = _as_workflow_state(
        graph.invoke(None, config={**config, "recursion_limit": 100})
    )

    assert resumed_result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert resumed_result.testing.passed is True
    assert llm_service.call_count("developer") > developer_calls_before_recovery


def test_get_state_returns_none_values_for_unknown_checkpoint(tmp_path: Path) -> None:
    run_id = generate_run_id()
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    checkpoint_service = CheckpointService(runs_root=tmp_path / "runs")
    checkpointer = checkpoint_service.checkpointer_for_run(run_id)

    graph, _ = _build_graph_and_nodes(output_directory, checkpointer)

    bogus_config = {
        "configurable": {
            "thread_id": run_id,
            "checkpoint_ns": "",
            "checkpoint_id": "does-not-exist",
        }
    }
    snapshot = graph.get_state(bogus_config)

    assert not snapshot.values
