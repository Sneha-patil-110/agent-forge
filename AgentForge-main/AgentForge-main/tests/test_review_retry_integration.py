
from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage

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
from backend.services.materialization_service import MaterializationService
from backend.services.testing_service import TestingService
from backend.state.execution_state import WorkflowStatus
from backend.state.workflow_state import WorkflowState
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry


class StubPromptService:
    def load(self, prompt_file: str) -> str:
        return f"SYSTEM PROMPT for {prompt_file}"


class ScriptedLLMService:

    def __init__(self, scripts: dict[str, list[dict]]) -> None:
        self._scripts = scripts
        self.calls: list[dict] = []
        self._call_index: dict[str, int] = {}

    def invoke(self, *, model_role, prompt, context, response_schema=None, extra_messages=None, **_):
        responses = self._scripts[model_role]
        index = self._call_index.get(model_role, 0)
        payload = responses[min(index, len(responses) - 1)]
        self._call_index[model_role] = index + 1

        self.calls.append(
            {"model_role": model_role, "prompt": prompt, "context": context}
        )

        return AIMessage(content=json.dumps(payload))

    def call_count(self, model_role: str) -> int:
        return self._call_index.get(model_role, 0)


VALID_PROJECT_STATE = {
    "project_name": "Calculator CLI",
    "project_description": "A command line calculator.",
    "objective": "Perform basic arithmetic from the CLI.",
    "requirements": ["Addition", "Division"],
    "backend": None,
    "frontend": None,
    "database": None,
    "deployment": None,
    "target_audience": "Developers",
    "pending_clarifications": [],
    "tech_stack": ["Python"],
    "output_directory": None,
    "status": "analyzed",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}

VALID_PLANNING_STATE = {
    "project_summary": "CLI calculator.",
    "implementation_strategy": "Single module implementation.",
    "tasks": [
        {
            "id": "T1",
            "title": "Implement operations",
            "description": "Implement add and divide.",
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
    "architecture_summary": "Single module CLI application.",
    "system_design": None,
    "folder_structure": None,
    "api_design": None,
    "components": [],
    "database_design": None,
    "design_patterns": [],
    "architecture_decisions": [],
}

TEST_FILE_CONTENT = (
    "import pytest\n"
    "from calc import divide\n"
    "\n"
    "\n"
    "def test_divide():\n"
    "    assert divide(6, 2) == 3\n"
    "\n"
    "\n"
    "def test_divide_by_zero():\n"
    "    with pytest.raises(ValueError):\n"
    "        divide(1, 0)\n"
)

WORKING_CALC_CONTENT = (
    "def divide(a, b):\n"
    "    if b == 0:\n"
    "        raise ValueError('Cannot divide by zero')\n"
    "    return a / b\n"
)

BROKEN_CALC_CONTENT = (
    "def divide(a, b):\n"
    "    return a / b\n"
)

ALWAYS_FAILING_TEST_CONTENT = (
    "def test_always_fails():\n"
    "    assert False, 'intentional failure for retry exhaustion test'\n"
)


def _implementation_payload(*files: dict) -> dict:
    return {
        "generated_code": list(files),
        "completed_tasks": ["T1"],
        "failed_tasks": [],
        "implementation_notes": "Implementation attempt.",
    }


def _calc_file(content: str, description: str) -> dict:
    return {
        "path": "calc.py",
        "content": content,
        "language": "python",
        "description": description,
    }


def _test_file(content: str = TEST_FILE_CONTENT) -> dict:
    return {
        "path": "test_calc.py",
        "content": content,
        "language": "python",
        "description": "Calculator tests.",
    }


TESTER_ANALYSIS = {
    "classification": "application_code_error",
    "summary": "test_divide_by_zero failed because ZeroDivisionError was not caught.",
    "affected_files": ["calc.py"],
    "evidence": "The test asserts ValueError is raised for a zero divisor; calc.py's divide() has no such check.",
    "recommended_action": "Validate the divisor in divide() before dividing.",
    "confidence": 0.9,
}

TEST_PLAN = TESTER_ANALYSIS

DEBUG_ANALYSIS = {
    "failure_summary": "test_divide_by_zero failed.",
    "root_cause": "divide() does not validate the divisor before dividing.",
    "failure_category": "code_defect",
    "affected_files": ["calc.py"],
    "repair_instructions": "Raise ValueError when the divisor is zero.",
    "suggested_changes": [
        {"file_path": "calc.py", "description": "Validate divisor is non-zero."}
    ],
    "confidence": 0.9,
    "attempt_number": 1,
    "debug_summary": "Missing zero-divisor validation.",
}

REVIEW_PASSED = {
    "passed": True,
    "score": 8.5,
    "issues": [],
    "strengths": ["Correct arithmetic."],
    "recommendations": [],
    "review_summary": "Implementation is correct.",
}

VALID_DOCUMENTATION_STATE = {
    "generated_docs": [
        {
            "title": "README",
            "path": "README.md",
            "content": "# Calculator CLI\n",
            "description": "Project overview.",
        }
    ],
    "documentation_summary": "Generated README.",
    "pending_documentation": [],
}


def _build_workflow(
    *,
    developer_script: list[dict],
    tester_script: list[dict],
    reviewer_script: list[dict],
    debugger_script: list[dict],
    output_directory: Path,
):
    llm_service = ScriptedLLMService(
        {
            "analysis": [VALID_PROJECT_STATE],
            "planner": [VALID_PLANNING_STATE],
            "architect": [VALID_ARCHITECTURE_STATE],
            "developer": developer_script,
            "tester": tester_script,
            "debugger": debugger_script,
            "reviewer": reviewer_script,
            "documentation": [VALID_DOCUMENTATION_STATE],
        }
    )
    prompt_service = StubPromptService()

    analysis_agent = AnalysisAgent(prompt_service, llm_service)
    planner_agent = PlannerAgent(prompt_service, llm_service)
    architect_agent = ArchitectAgent(prompt_service, llm_service)
    developer_agent = DeveloperAgent(prompt_service, llm_service)
    tester_agent = TesterAgent(prompt_service, llm_service)
    debugger_agent = DebuggerAgent(prompt_service, llm_service)
    reviewer_agent = ReviewerAgent(prompt_service, llm_service)
    documentation_agent = DocumentationAgent(prompt_service, llm_service)

    tool_registry = ToolRegistry()
    tool_registry.register(FilesystemTool(workspace=output_directory))
    tool_registry.register(TerminalTool(workspace=output_directory))

    materialization_service = MaterializationService(tool_registry)
    testing_service = TestingService(tool_registry)

    nodes = WorkflowNodes(
        analysis_agent=analysis_agent,
        planner_agent=planner_agent,
        architect_agent=architect_agent,
        developer_agent=developer_agent,
        tester_agent=tester_agent,
        debugger_agent=debugger_agent,
        reviewer_agent=reviewer_agent,
        documentation_agent=documentation_agent,
        materialization_service=materialization_service,
        testing_service=testing_service,
    )

    graph = WorkflowBuilder(nodes).build()

    return graph, llm_service


def _initial_state(output_directory: Path) -> WorkflowState:
    state = WorkflowState()
    state.project.output_directory = str(output_directory)
    return state


def _as_workflow_state(result) -> WorkflowState:
    return (
        result
        if isinstance(result, WorkflowState)
        else WorkflowState.model_validate(result)
    )


def test_case_a_everything_passes_first_attempt(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, llm_service = _build_workflow(
        developer_script=[
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module."),
                _test_file(),
            )
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert llm_service.call_count("developer") == 1
    assert llm_service.call_count("tester") == 0
    assert llm_service.call_count("debugger") == 0
    assert llm_service.call_count("reviewer") == 1
    assert llm_service.call_count("documentation") == 1

    assert result.testing.passed is True
    assert result.testing.exit_code == 0
    assert result.review.passed is True
    assert result.execution.test_retry_count == 0
    assert result.execution.review_retry_count == 0
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert result.documentation.generated_docs[0].path == "README.md"
    assert set(result.implementation.written_files) == {"calc.py", "test_calc.py"}


def test_case_b_test_fails_once_then_passes(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, llm_service = _build_workflow(
        developer_script=[
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT, "Calculator module (buggy)."),
                _test_file(),
            ),
            _implementation_payload(
                _calc_file(WORKING_CALC_CONTENT, "Calculator module (fixed)."),
            ),
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(graph.invoke(_initial_state(output_directory)))

    assert llm_service.call_count("developer") == 2
    assert llm_service.call_count("tester") == 1
    assert llm_service.call_count("debugger") == 1
    assert llm_service.call_count("reviewer") == 1
    assert llm_service.call_count("documentation") == 1

    assert result.execution.test_retry_count == 1
    assert result.execution.review_retry_count == 0
    assert result.testing.passed is True
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED

    debugger_context = llm_service.calls[
        [c["model_role"] for c in llm_service.calls].index("debugger")
    ]["context"]
    assert "ZeroDivisionError" in debugger_context or "FAILED" in debugger_context
    assert "test_divide_by_zero" in debugger_context

    developer_calls = [c for c in llm_service.calls if c["model_role"] == "developer"]
    second_developer_context = developer_calls[1]["context"]
    assert "Debug Feedback" in second_developer_context
    assert "Review Feedback" not in second_developer_context
    assert "divide() does not validate the divisor" in second_developer_context

    assert (output_directory / "calc.py").read_text(encoding="utf-8") == (
        WORKING_CALC_CONTENT
    )
    assert (output_directory / "test_calc.py").exists()
    assert set(result.implementation.written_files) == {"calc.py", "test_calc.py"}


def test_case_c_tests_fail_until_retry_exhaustion(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()

    developer_script = [
        _implementation_payload(
            _calc_file(
                BROKEN_CALC_CONTENT + f"\n# repair attempt {attempt}\n",
                "Calculator module.",
            ),
            _test_file(ALWAYS_FAILING_TEST_CONTENT),
        )
        for attempt in range(MAX_TEST_RETRIES + 1)
    ]

    graph, llm_service = _build_workflow(
        developer_script=developer_script,
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(
        graph.invoke(
            _initial_state(output_directory),
            config={"recursion_limit": 100},
        )
    )

    assert llm_service.call_count("reviewer") == 0
    assert llm_service.call_count("documentation") == 0
    assert result.testing.passed is False
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert result.execution.test_retry_count == MAX_TEST_RETRIES + 1
    assert result.execution.review_retry_count == 0

    assert llm_service.call_count("developer") == MAX_TEST_RETRIES + 1
    assert llm_service.call_count("tester") == MAX_TEST_RETRIES + 1
    assert llm_service.call_count("debugger") == MAX_TEST_RETRIES

    assert result.execution.error_message is not None
    assert "retries" in result.execution.error_message.lower()


def test_no_effect_repair_stops_the_loop_before_retry_exhaustion(tmp_path: Path) -> None:

    output_directory = tmp_path / "project"
    output_directory.mkdir()

    graph, llm_service = _build_workflow(
        developer_script=[
            _implementation_payload(
                _calc_file(BROKEN_CALC_CONTENT, "Calculator module."),
                _test_file(ALWAYS_FAILING_TEST_CONTENT),
            )
        ],
        tester_script=[TESTER_ANALYSIS],
        reviewer_script=[REVIEW_PASSED],
        debugger_script=[DEBUG_ANALYSIS],
        output_directory=output_directory,
    )

    result = _as_workflow_state(
        graph.invoke(
            _initial_state(output_directory),
            config={"recursion_limit": 100},
        )
    )

    assert result.testing.passed is False
    assert result.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert result.execution.test_retry_count == 1
    assert "no code changes" in result.execution.error_message.lower()
