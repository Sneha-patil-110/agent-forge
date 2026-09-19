from __future__ import annotations

from contextlib import contextmanager

import pytest
from langchain_core.messages import AIMessage

from backend.core.exceptions import LLMError
from backend.services.llm_service import LLMService


class _RecordingModel:
    def __init__(self, response: AIMessage) -> None:
        self._response = response
        self.invoked_messages = None

    def invoke(self, messages):
        self.invoked_messages = messages
        return self._response


class _BrokenModel:
    def invoke(self, messages):
        raise RuntimeError("provider unreachable")


class _StubModelRegistry:
    def __init__(self, model, *, config: dict | None = None) -> None:
        self._model = model
        self.config = config or {}

    def get_model(self, role: str):
        return self._model


class _FakeTracingService:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.outputs: list[tuple[dict, dict]] = []

    @contextmanager
    def trace(self, name, *, run_type="chain", tags=None, metadata=None, inputs=None):
        record = {"name": name, "run_type": run_type, "tags": tags, "metadata": metadata}
        self.calls.append(record)

        try:
            yield record
        except BaseException as error:
            record["error"] = repr(error)
            raise

    def set_outputs(self, run, outputs) -> None:
        if run is None:
            return

        self.outputs.append((run, outputs))


def test_invoke_without_a_tracing_service_behaves_exactly_as_before() -> None:
    model = _RecordingModel(AIMessage(content="hello"))
    service = LLMService(_StubModelRegistry(model))

    result = service.invoke(model_role="analysis", prompt="p", context="c")

    assert result.content == "hello"
    assert model.invoked_messages is not None


def test_invoke_opens_an_llm_span_with_role_and_provider_metadata() -> None:
    model = _RecordingModel(AIMessage(content="hello world"))
    registry = _StubModelRegistry(
        model, config={"analysis": {"provider": "cerebras", "model": "gpt-oss-120b"}}
    )
    tracing = _FakeTracingService()
    service = LLMService(registry, tracing_service=tracing)

    service.invoke(model_role="analysis", prompt="prompt-text", context="context-text")

    assert len(tracing.calls) == 1
    call = tracing.calls[0]
    assert call["name"] == "llm:analysis"
    assert call["run_type"] == "llm"
    assert "agent:analysis" in call["tags"]
    assert "provider:cerebras" in call["tags"]
    assert call["metadata"]["provider"] == "cerebras"
    assert call["metadata"]["model"] == "gpt-oss-120b"
    assert call["metadata"]["model_role"] == "analysis"
    assert call["metadata"]["prompt_chars"] == len("prompt-text") + len("context-text")


def test_invoke_records_completion_size_and_latency_on_success() -> None:
    model = _RecordingModel(AIMessage(content="hello world"))
    tracing = _FakeTracingService()
    service = LLMService(_StubModelRegistry(model), tracing_service=tracing)

    service.invoke(model_role="analysis", prompt="p", context="c")

    assert len(tracing.outputs) == 1
    _, outputs = tracing.outputs[0]
    assert outputs["completion_chars"] == len("hello world")
    assert outputs["latency_ms"] >= 0


def test_invoke_failure_propagates_as_llm_error_and_is_visible_to_the_span() -> None:
    registry = _StubModelRegistry(_BrokenModel())
    tracing = _FakeTracingService()
    service = LLMService(registry, tracing_service=tracing)

    with pytest.raises(LLMError):
        service.invoke(model_role="analysis", prompt="p", context="c")

    assert "error" in tracing.calls[0]
    assert tracing.outputs == []


def test_invoke_with_model_registry_lacking_config_attribute_does_not_crash() -> None:
    class _BareRegistry:
        def get_model(self, role: str):
            return _RecordingModel(AIMessage(content="ok"))

    tracing = _FakeTracingService()
    service = LLMService(_BareRegistry(), tracing_service=tracing)

    result = service.invoke(model_role="analysis", prompt="p", context="c")

    assert result.content == "ok"
    assert tracing.calls[0]["metadata"]["provider"] is None