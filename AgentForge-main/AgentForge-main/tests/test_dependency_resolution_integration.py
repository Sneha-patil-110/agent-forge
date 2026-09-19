
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
from backend.graph.builder import WorkflowBuilder
from backend.graph.nodes import WorkflowNodes
from backend.services.dependency_preparation_service import DependencyPreparationService
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import FailureCategory, RepairTrigger, WorkflowStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry

from tests.test_review_retry_integration import (
    DEBUG_ANALYSIS,
    REVIEW_PASSED,
    VALID_ARCHITECTURE_STATE,
    VALID_DOCUMENTATION_STATE,
    VALID_PLANNING_STATE,
    VALID_PROJECT_STATE,
    ScriptedLLMService,
    StubPromptService,
    _as_workflow_state,
    _implementation_payload,
    _initial_state,
)

TEST_FILE_CONTENT = (
    "def test_add():\n"
    "    from calc import add\n"
    "    assert add(2, 3) == 5\n"
)

CALC_CONTENT = "def add(a, b):\n    return a + b\n"


def _file(path: str, content: str, description: str) -> dict:
    return {"path": path, "content": content, "language": "python", "description": description}


BROKEN_REQUIREMENTS = "this-package-definitely-does-not-exist-ever-12345==1.0.0\n"
FIXED_REQUIREMENTS = "six\n"

DEVELOPER_ATTEMPT_1 = _implementation_payload(
    _file("calc.py", CALC_CONTENT, "Calculator module."),
    _file("test_calc.py", TEST_FILE_CONTENT, "Calculator tests."),
    _file("requirements.txt", BROKEN_REQUIREMENTS, "Dependencies (broken)."),
)

DEVELOPER_ATTEMPT_2 = _implementation_payload(
    _file("requirements.txt", FIXED_REQUIREMENTS, "Dependencies (fixed)."),
)


def _build_workflow(output_directory: Path):
    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": [DEVELOPER_ATTEMPT_1, DEVELOPER_ATTEMPT_2],
            "tester": [],
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
        dependency_preparation_service=DependencyPreparationService(
            tool_registry, retry_delay_seconds=0
        ),
    )

    graph = WorkflowBuilder(nodes).build()

    return graph, llm_service


def test_genuine_dependency_error_is_repaired_and_workflow_completes(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, llm_service = _build_workflow(output_directory)

    result = _as_workflow_state(
        graph.invoke(_initial_state(output_directory), config={"recursion_limit": 100})
    )

    assert llm_service.call_count("developer") == 2
    assert llm_service.call_count("debugger") == 1
    assert llm_service.call_count("tester") == 0
    assert llm_service.call_count("reviewer") == 1

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert result.testing.passed is True
    assert result.testing.tests_executed is True

    assert result.execution.dependency_retry_count == 1
    assert result.execution.test_retry_count == 0

    assert (output_directory / "requirements.txt").read_text(encoding="utf-8") == FIXED_REQUIREMENTS

    assert (output_directory / ".venv").exists()
