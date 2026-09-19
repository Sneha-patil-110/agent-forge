from __future__ import annotations

import json

import pytest
from langchain_core.messages import AIMessage

from backend.agents.debugger_agent import DebuggerAgent
from backend.core.exceptions import AgentValidationError
from backend.state.execution_state import WorkflowStatus
from backend.state.implementation_state import GeneratedCode
from backend.state.testing_state import TestFailure, TestStatus
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


VALID_DEBUG_PAYLOAD = {
    "failure_summary": "test_divide_by_zero failed.",
    "root_cause": "divide() does not validate the divisor.",
    "failure_category": "code_defect",
    "affected_files": ["calc.py"],
    "repair_instructions": "Raise ValueError when dividing by zero.",
    "suggested_changes": [
        {"file_path": "calc.py", "description": "Validate divisor is non-zero."}
    ],
    "confidence": 0.9,
    "attempt_number": 1,
    "debug_summary": "Missing zero-divisor validation.",
}


def _make_agent(content: str):
    prompt_service = RecordingPromptService()
    llm_service = RecordingLLMService(content)
    return DebuggerAgent(prompt_service, llm_service), prompt_service, llm_service


def _state_with_failed_test() -> WorkflowState:
    state = WorkflowState()
    state.implementation.generated_code = [
        GeneratedCode(path="calc.py", content="def divide(a,b): return a/b", language="python")
    ]
    state.testing.status = TestStatus.FAILED
    state.testing.command = ["python", "-m", "pytest"]
    state.testing.exit_code = 1
    state.testing.stdout = "FAILED test_calc.py::test_divide_by_zero"
    state.testing.stderr = "ZeroDivisionError: division by zero"
    state.testing.failed_tests = [TestFailure(name="test_calc.py::test_divide_by_zero")]
    return state


def test_loads_correct_prompt_file() -> None:
    agent, prompt_service, _ = _make_agent(json.dumps(VALID_DEBUG_PAYLOAD))

    agent.run(_state_with_failed_test())

    assert prompt_service.loaded == ["debugger.md"]


def test_selects_correct_model_role() -> None:
    agent, _, llm_service = _make_agent(json.dumps(VALID_DEBUG_PAYLOAD))

    agent.run(_state_with_failed_test())

    assert llm_service.calls[0]["model_role"] == "debugger"


def test_context_includes_project_architecture_implementation_and_testing_evidence() -> None:
    agent, _, llm_service = _make_agent(json.dumps(VALID_DEBUG_PAYLOAD))

    state = _state_with_failed_test()
    state.project.project_name = "Calculator CLI"
    state.architecture.architecture_summary = "Single module."

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Calculator CLI" in context
    assert "Single module." in context
    assert "calc.py" in context
    assert "ZeroDivisionError" in context
    assert "test_divide_by_zero" in context
    assert '"exit_code": 1' in context


def test_valid_response_produces_debug_state() -> None:
    agent, _, _ = _make_agent(json.dumps(VALID_DEBUG_PAYLOAD))

    result = agent.run(_state_with_failed_test())

    assert result.debug.root_cause == "divide() does not validate the divisor."
    assert result.debug.failure_category.value == "code_defect"
    assert result.debug.affected_files == ["calc.py"]
    assert result.debug.confidence == 0.9


def test_attempt_number_is_overridden_by_application_tracked_count() -> None:

    payload = dict(VALID_DEBUG_PAYLOAD)
    payload["attempt_number"] = 999

    agent, _, _ = _make_agent(json.dumps(payload))

    state = _state_with_failed_test()
    state.execution.test_retry_count = 2

    result = agent.run(state)

    assert result.debug.attempt_number == 2


def test_invalid_json_raises_agent_validation_error() -> None:
    agent, _, _ = _make_agent("not json at all")

    with pytest.raises(AgentValidationError):
        agent.run(_state_with_failed_test())


def test_schema_mismatch_raises_agent_validation_error() -> None:
    agent, _, _ = _make_agent(json.dumps({"confidence": 5.0}))

    with pytest.raises(AgentValidationError):
        agent.run(_state_with_failed_test())


def test_exception_updates_execution_state_and_is_not_swallowed() -> None:
    agent, _, _ = _make_agent("")

    state = _state_with_failed_test()

    with pytest.raises(AgentValidationError):
        agent.run(state)

    assert state.execution.workflow_status == WorkflowStatus.FAILED
    assert state.execution.current_step == "Failed during debugger agent"


def test_previous_debug_analysis_included_on_repeat_failure() -> None:
    agent, _, llm_service = _make_agent(json.dumps(VALID_DEBUG_PAYLOAD))

    state = _state_with_failed_test()
    state.debug.failure_summary = "Earlier analysis of a prior failure."
    state.debug.root_cause = "An earlier, different root cause."

    agent.run(state)

    context = llm_service.calls[0]["context"]

    assert "Previous Debug Analysis" in context
    assert "An earlier, different root cause." in context
