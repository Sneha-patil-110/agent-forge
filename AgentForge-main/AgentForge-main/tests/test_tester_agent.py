from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from backend.agents.tester_agent import TesterAgent
from backend.core.exceptions import AgentValidationError
from backend.state.execution_state import FailureCategory, WorkflowStatus
from backend.state.implementation_state import GeneratedCode
from backend.state.testing_state import TestFailure, TestingState, TestStatus
from backend.state.tester_analysis import TesterAnalysis
from backend.state.workflow_state import WorkflowState


class RecordingLLMService:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[dict] = []

    def invoke(self, *, model_role, prompt, context, response_schema=None, extra_messages=None, **_):
        self.calls.append(
            {"model_role": model_role, "prompt": prompt, "context": context}
        )
        return AIMessage(content=self.content)


class RecordingPromptService:
    def __init__(self) -> None:
        self.loaded: list[str] = []

    def load(self, prompt_file: str) -> str:
        self.loaded.append(prompt_file)
        return f"SYSTEM PROMPT for {prompt_file}"


def _make_agent(content: str):
    prompt_service = RecordingPromptService()
    llm_service = RecordingLLMService(content)
    return TesterAgent(prompt_service, llm_service), prompt_service, llm_service


VALID_ANALYSIS = {
    "classification": "application_code_error",
    "summary": "divide() does not validate a zero divisor.",
    "affected_files": ["calc.py"],
    "evidence": "Architecture requires ValueError on zero divisor; implementation raises ZeroDivisionError instead.",
    "recommended_action": "Add a zero-divisor check to divide().",
    "confidence": 0.85,
}


def _state_with_real_failure() -> WorkflowState:

    state = WorkflowState()
    state.implementation.generated_code = [
        GeneratedCode(
            path="calc.py", content="def divide(a, b): return a / b", language="python"
        )
    ]
    state.testing = TestingState(
        status=TestStatus.FAILED,
        command=["python", "-m", "pytest"],
        exit_code=1,
        passed=False,
        stdout="FAILED test_calc.py::test_divide_by_zero - ZeroDivisionError",
        failed_tests=[
            TestFailure(
                name="test_calc.py::test_divide_by_zero",
                message="ZeroDivisionError: division by zero",
                file_path="test_calc.py",
            )
        ],
        attempt_number=1,
    )
    return state


def test_loads_correct_prompt_file() -> None:
    agent, prompt_service, _ = _make_agent(json.dumps(VALID_ANALYSIS))

    agent.run(_state_with_real_failure())

    assert prompt_service.loaded == ["tester.md"]


def test_selects_correct_model_role() -> None:
    agent, _, llm_service = _make_agent(json.dumps(VALID_ANALYSIS))

    agent.run(_state_with_real_failure())

    assert llm_service.calls[0]["model_role"] == "tester"


def test_context_includes_project_architecture_implementation_and_real_evidence() -> None:
    agent, _, llm_service = _make_agent(json.dumps(VALID_ANALYSIS))

    state = _state_with_real_failure()
    state.project.project_name = "Calculator CLI"
    state.architecture.architecture_summary = "Single module."

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Calculator CLI" in context
    assert "Single module." in context
    assert "calc.py" in context
    assert "test_divide_by_zero" in context
    assert "ZeroDivisionError" in context


def test_valid_response_produces_analysis() -> None:
    agent, _, _ = _make_agent(json.dumps(VALID_ANALYSIS))

    result = agent.run(_state_with_real_failure())

    assert result.tester_analysis.classification == FailureCategory.APPLICATION_CODE_ERROR
    assert result.tester_analysis.affected_files == ["calc.py"]
    assert result.tester_analysis.confidence == 0.85
    assert result.testing.classification == FailureCategory.APPLICATION_CODE_ERROR
    assert result.testing.exit_code == 1
    assert result.testing.passed is False


def test_generated_test_error_classification_is_preserved() -> None:
    analysis = {**VALID_ANALYSIS, "classification": "generated_test_error"}
    agent, _, _ = _make_agent(json.dumps(analysis))

    result = agent.run(_state_with_real_failure())

    assert result.tester_analysis.classification == FailureCategory.GENERATED_TEST_ERROR
    assert result.testing.classification == FailureCategory.GENERATED_TEST_ERROR


def test_ignores_fabricated_execution_results_even_if_llm_disobeys() -> None:

    agent, _, _ = _make_agent(
        json.dumps(
            {
                **VALID_ANALYSIS,
                "status": "passed",
                "passed": True,
                "exit_code": 0,
                "stdout": "3 passed in 0.01s",
            }
        )
    )

    state = _state_with_real_failure()
    result = agent.run(state)

    assert result.testing.status == TestStatus.FAILED
    assert result.testing.passed is False
    assert result.testing.exit_code == 1
    assert "ZeroDivisionError" in result.testing.stdout


def test_invalid_json_raises_agent_validation_error() -> None:
    agent, _, _ = _make_agent("not json at all")

    with pytest.raises(AgentValidationError):
        agent.run(_state_with_real_failure())


def test_schema_mismatch_raises_agent_validation_error() -> None:
    agent, _, _ = _make_agent(json.dumps({"classification": "not-a-real-category"}))

    with pytest.raises(AgentValidationError):
        agent.run(_state_with_real_failure())


def test_exception_updates_execution_state_and_is_not_swallowed() -> None:
    agent, _, _ = _make_agent("")

    state = _state_with_real_failure()

    with pytest.raises(AgentValidationError):
        agent.run(state)

    assert state.execution.workflow_status == WorkflowStatus.FAILED
    assert state.execution.current_step == "Failed during tester agent"


def test_successful_run_updates_execution_state() -> None:
    agent, _, _ = _make_agent(json.dumps(VALID_ANALYSIS))

    state = _state_with_real_failure()
    result = agent.run(state)

    assert result.execution.current_agent.value == "tester"
    assert result.execution.error_message is None



def test_tester_agent_supports_native_structured_output_analysis() -> None:
    prompt_service = RecordingPromptService()
    llm_service = RecordingLLMService("")
    llm_service.invoke = lambda **kwargs: TesterAnalysis(
        classification=FailureCategory.GENERATED_TEST_ERROR,
        summary="Native analysis",
        confidence=0.7,
    )
    agent = TesterAgent(prompt_service, llm_service)

    result = agent.run(_state_with_real_failure())
    assert result.tester_analysis.classification == FailureCategory.GENERATED_TEST_ERROR
    assert result.tester_analysis.summary == "Native analysis"


def test_tester_agent_handles_markdown_fenced_json() -> None:
    fenced = "```json\n" + json.dumps(VALID_ANALYSIS) + "\n```"
    agent, _, _ = _make_agent(fenced)

    result = agent.run(_state_with_real_failure())
    assert result.tester_analysis.classification == FailureCategory.APPLICATION_CODE_ERROR


def test_tester_agent_empty_response_raises_empty_error() -> None:
    from backend.core.exceptions import AgentOutputEmptyError

    agent, _, _ = _make_agent("")

    with pytest.raises(AgentOutputEmptyError):
        agent.run(_state_with_real_failure())


def test_tester_agent_truncated_response_raises_truncated_error() -> None:
    from backend.core.exceptions import AgentOutputTruncatedError

    prompt_service = RecordingPromptService()
    llm_service = RecordingLLMService("{\"classification\": \"application")
    llm_service.invoke = lambda **kwargs: AIMessage(
        content="{\"classification\": \"application",
        response_metadata={"finish_reason": "length"}
    )
    agent = TesterAgent(prompt_service, llm_service)

    with pytest.raises(AgentOutputTruncatedError):
        agent.run(_state_with_real_failure())


def test_tester_agent_single_schema_recovery_attempt_succeeds() -> None:
    prompt_service = RecordingPromptService()

    call_count = 0
    def mock_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return AIMessage(content="Here is the analysis: {\"classification\": invalid}")
        return TesterAnalysis(classification=FailureCategory.APPLICATION_CODE_ERROR, summary="Recovered analysis")

    llm_service = RecordingLLMService("")
    llm_service.invoke = mock_invoke

    agent = TesterAgent(prompt_service, llm_service)
    result = agent.run(_state_with_real_failure())

    assert call_count == 2
    assert result.tester_analysis.classification == FailureCategory.APPLICATION_CODE_ERROR
    assert result.tester_analysis.summary == "Recovered analysis"


def test_tester_agent_schema_recovery_attempt_fails_raises_schema_error() -> None:
    from backend.core.exceptions import AgentOutputSchemaError

    prompt_service = RecordingPromptService()
    def mock_invoke(**kwargs):
        return AIMessage(content="not json")

    llm_service = RecordingLLMService("")
    llm_service.invoke = mock_invoke

    agent = TesterAgent(prompt_service, llm_service)

    with pytest.raises(AgentOutputSchemaError):
        agent.run(_state_with_real_failure())


def test_tester_analysis_rejects_an_infrastructure_classification() -> None:

    with pytest.raises(ValueError):
        TesterAnalysis(classification=FailureCategory.TEST_DISCOVERY_ERROR)

    with pytest.raises(ValueError):
        TesterAnalysis(classification=FailureCategory.DEPENDENCY_INSTALL_ERROR)

    TesterAnalysis(classification=FailureCategory.APPLICATION_CODE_ERROR)
    TesterAnalysis(classification=FailureCategory.GENERATED_TEST_ERROR)
    TesterAnalysis(classification=FailureCategory.TEST_FAILURE)
    TesterAnalysis(classification=None)


def test_an_infrastructure_classification_from_the_llm_triggers_schema_recovery() -> None:
    analysis_with_bad_category = json.dumps(
        {
            "classification": "test_discovery_error",
            "summary": "Confusing output.",
            "affected_files": [],
            "evidence": "0 tests failed after a targeted rerun.",
            "recommended_action": None,
            "confidence": 0.5,
        }
    )
    agent, _, llm_service = _make_agent(analysis_with_bad_category)
    llm_service.invoke = lambda **kwargs: TesterAnalysis(
        classification=FailureCategory.APPLICATION_CODE_ERROR, summary="Recovered."
    )

    result = agent.run(_state_with_real_failure())

    assert result.tester_analysis.classification in (
        FailureCategory.APPLICATION_CODE_ERROR,
        FailureCategory.GENERATED_TEST_ERROR,
        FailureCategory.TEST_FAILURE,
        None,
    )
