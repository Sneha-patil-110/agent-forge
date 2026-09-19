from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from backend.agents.base_agent import BaseAgent
from backend.core.exceptions import AgentExecutionError, AgentValidationError
from backend.state.execution_state import WorkflowStatus
from backend.state.workflow_state import WorkflowState


class _StubLLMService:
    def __init__(self, content: str = "ok") -> None:
        self.content = content
        self.calls: list[dict] = []

    def invoke(
        self, *, model_role: str, prompt: str, context: str, response_schema=None, extra_messages=None, **_
    ) -> AIMessage:
        self.calls.append({"extra_messages": extra_messages})
        return AIMessage(content=self.content)


class _StubPromptService:
    def load(self, prompt_file: str) -> str:
        return "system prompt"


class _EchoAgent(BaseAgent[str]):
    def __init__(self, *, agent_name: str, llm_service, fail: bool = False) -> None:
        super().__init__(_StubPromptService(), llm_service)
        self._agent_name = agent_name
        self._fail = fail

    @property
    def name(self) -> str:
        return self._agent_name

    @property
    def prompt_file(self) -> str:
        return "stub.md"

    @property
    def model_role(self) -> str:
        return self._agent_name

    def build_context(self, state: WorkflowState) -> str:
        return "context"

    def validate(self, response: AIMessage) -> str:
        if self._fail:
            raise AgentValidationError("stub failure")

        return response.content

    def update_state(self, state: WorkflowState, validated_output: str) -> WorkflowState:
        return state


def test_run_marks_workflow_running_and_completes_step() -> None:
    agent = _EchoAgent(agent_name="analysis", llm_service=_StubLLMService())
    state = WorkflowState()

    result = agent.run(state)

    assert result.execution.workflow_status == WorkflowStatus.RUNNING
    assert result.execution.current_step == "Completed analysis agent"


def test_documentation_agent_marks_workflow_completed() -> None:
    agent = _EchoAgent(agent_name="documentation", llm_service=_StubLLMService())
    state = WorkflowState()

    result = agent.run(state)

    assert result.execution.workflow_status == WorkflowStatus.COMPLETED
    assert result.execution.completed_at is not None


def test_failure_marks_workflow_failed_and_reraises_agentforge_error() -> None:
    agent = _EchoAgent(
        agent_name="analysis", llm_service=_StubLLMService(), fail=True
    )
    state = WorkflowState()

    with pytest.raises(AgentValidationError):
        agent.run(state)

    assert state.execution.workflow_status == WorkflowStatus.FAILED
    assert state.execution.error_message is not None


def test_failure_still_stops_after_one_repair_attempt() -> None:
    llm_service = _StubLLMService()
    agent = _EchoAgent(agent_name="analysis", llm_service=llm_service, fail=True)
    state = WorkflowState()

    with pytest.raises(AgentValidationError):
        agent.run(state)

    assert len(llm_service.calls) == 2
    assert llm_service.calls[0]["extra_messages"] is None
    assert llm_service.calls[1]["extra_messages"] is not None


class _FlakyOnceAgent(BaseAgent[str]):
    def __init__(self, *, llm_service) -> None:
        super().__init__(_StubPromptService(), llm_service)
        self._validate_calls = 0

    @property
    def name(self) -> str:
        return "analysis"

    @property
    def prompt_file(self) -> str:
        return "stub.md"

    @property
    def model_role(self) -> str:
        return "analysis"

    def build_context(self, state: WorkflowState) -> str:
        return "context"

    def validate(self, response: AIMessage) -> str:
        self._validate_calls += 1
        if self._validate_calls == 1:
            raise AgentValidationError("first attempt returned malformed output")
        return response.content

    def update_state(self, state: WorkflowState, validated_output: str) -> WorkflowState:
        return state


def test_agent_recovers_from_one_bad_output_via_correction_retry() -> None:
    llm_service = _StubLLMService()
    agent = _FlakyOnceAgent(llm_service=llm_service)
    state = WorkflowState()

    result = agent.run(state)

    assert result.execution.workflow_status == WorkflowStatus.RUNNING
    assert len(llm_service.calls) == 2
    assert llm_service.calls[0]["extra_messages"] is None
    correction = llm_service.calls[1]["extra_messages"]
    assert correction is not None
    assert "malformed output" in correction[-1].content


def test_unexpected_error_is_wrapped_with_agent_context() -> None:
    class _BrokenLLMService:
        def invoke(self, **_: object) -> AIMessage:
            raise RuntimeError("boom")

    agent = _EchoAgent(agent_name="analysis", llm_service=_BrokenLLMService())
    state = WorkflowState()

    with pytest.raises(AgentExecutionError) as exc_info:
        agent.run(state)

    assert "analysis" in str(exc_info.value)
    assert state.execution.workflow_status == WorkflowStatus.FAILED
