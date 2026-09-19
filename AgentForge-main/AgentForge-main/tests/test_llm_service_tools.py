from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from backend.services.llm_service import LLMService


class _RecordingModel:
    def __init__(self, response: AIMessage) -> None:
        self._response = response
        self.bound_tools = None
        self.invoked_messages: list[BaseMessage] | None = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        return self

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.invoked_messages = messages
        return self._response


class _StubModelRegistry:
    def __init__(self, model) -> None:
        self._model = model

    def get_model(self, role: str):
        return self._model


def test_invoke_without_tools_does_not_bind_anything() -> None:
    model = _RecordingModel(AIMessage(content="hello"))
    service = LLMService(_StubModelRegistry(model))

    service.invoke(model_role="analysis", prompt="p", context="c")

    assert model.bound_tools is None


def test_invoke_with_tools_binds_schemas() -> None:
    model = _RecordingModel(AIMessage(content="hello"))
    service = LLMService(_StubModelRegistry(model))

    schema = {"type": "function", "function": {"name": "docs.search", "description": "d", "parameters": {}}}
    service.invoke(model_role="documentation", prompt="p", context="c", tools=[schema])

    assert model.bound_tools == [schema]


def test_invoke_appends_extra_messages() -> None:
    model = _RecordingModel(AIMessage(content="final"))
    service = LLMService(_StubModelRegistry(model))

    extra = [
        AIMessage(content="", tool_calls=[{"name": "docs.search", "args": {}, "id": "1"}]),
        ToolMessage(content="result text", tool_call_id="1"),
    ]

    service.invoke(model_role="documentation", prompt="p", context="c", extra_messages=extra)

    assert model.invoked_messages[-2:] == extra
    assert len(model.invoked_messages) == 4


def test_invoke_returns_tool_calls_when_model_requests_them() -> None:
    response = AIMessage(content="", tool_calls=[{"name": "docs.search", "args": {"q": "x"}, "id": "1"}])
    model = _RecordingModel(response)
    service = LLMService(_StubModelRegistry(model))

    result = service.invoke(model_role="documentation", prompt="p", context="c", tools=[{}])

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0]["name"] == "docs.search"
    assert result.tool_calls[0]["args"] == {"q": "x"}
    assert result.tool_calls[0]["id"] == "1"


def test_invoke_normalizes_list_content_blocks_to_a_string() -> None:

    response = AIMessage(
        content=[
            {"type": "text", "text": '{"key": '},
            {"type": "text", "text": '"value"}'},
        ]
    )
    model = _RecordingModel(response)
    service = LLMService(_StubModelRegistry(model))

    result = service.invoke(model_role="developer", prompt="p", context="c")

    assert result.content == '{"key": "value"}'
    assert isinstance(result.content, str)


def test_invoke_drops_non_text_content_blocks() -> None:
    response = AIMessage(
        content=[
            {"type": "text", "text": "real answer"},
            {"type": "thinking", "thinking": "internal reasoning, not the answer"},
        ]
    )
    model = _RecordingModel(response)
    service = LLMService(_StubModelRegistry(model))

    result = service.invoke(model_role="developer", prompt="p", context="c")

    assert result.content == "real answer"


def test_invoke_leaves_plain_string_content_untouched() -> None:
    model = _RecordingModel(AIMessage(content='{"already": "a string"}'))
    service = LLMService(_StubModelRegistry(model))

    result = service.invoke(model_role="developer", prompt="p", context="c")

    assert result.content == '{"already": "a string"}'


def test_invoke_does_not_normalize_structured_output_result() -> None:

    from pydantic import BaseModel

    class _Schema(BaseModel):
        content: list[str] = ["not", "message", "blocks"]

    parsed = _Schema()
    model = _RecordingModel(parsed)
    service = LLMService(_StubModelRegistry(model))

    result = service.invoke(model_role="developer", prompt="p", context="c", response_schema=_Schema)

    assert result.content == ["not", "message", "blocks"]
