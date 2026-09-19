from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from backend.tools.base_tool import BaseTool, ToolResult


class _FakeTracingService:
    def __init__(self) -> None:
        self.spans: list[dict] = []

    @contextmanager
    def trace(self, name, *, run_type="chain", tags=None, metadata=None, inputs=None):
        entry = {"name": name, "run_type": run_type, "tags": tags, "metadata": metadata}
        self.spans.append(entry)

        try:
            yield entry
        except BaseException as error:
            entry["error"] = repr(error)
            raise

    def set_outputs(self, run, outputs, *, error=None) -> None:
        if run is None:
            return

        run["outputs"] = outputs
        run["explicit_error"] = error


class _EchoTool(BaseTool):
    def __init__(self, *, tracing_service=None, fail: bool = False) -> None:
        super().__init__(tracing_service=tracing_service)
        self._fail = fail

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return "echoes its arguments"

    def execute(self, **kwargs: Any) -> ToolResult:
        if self._fail:
            raise RuntimeError("disk is full")

        return ToolResult(success=True, output=kwargs.get("content", ""))


def test_run_without_a_tracing_service_behaves_exactly_as_before() -> None:
    tool = _EchoTool()

    result = tool.run(operation="write", path="a.txt", content="hello")

    assert result.success is True
    assert result.output == "hello"


def test_run_opens_a_tool_span_with_name_type_category_and_argument_count() -> None:
    tracing = _FakeTracingService()
    tool = _EchoTool(tracing_service=tracing)

    tool.run(operation="write", path="a.txt", content="hello")

    assert len(tracing.spans) == 1
    span = tracing.spans[0]
    assert span["name"] == "tool:filesystem"
    assert span["run_type"] == "tool"
    assert span["tags"] == ["tool:filesystem"]
    assert span["metadata"]["tool_name"] == "filesystem"
    assert span["metadata"]["tool_type"] == "_EchoTool"
    assert span["metadata"]["tool_category"] == "filesystem"
    assert span["metadata"]["argument_count"] == 3


def test_run_records_success_and_result_size_without_leaking_raw_output() -> None:
    tracing = _FakeTracingService()
    tool = _EchoTool(tracing_service=tracing)

    tool.run(operation="write", path="a.txt", content="hello world")

    outputs = tracing.spans[0]["outputs"]
    assert outputs["success"] is True
    assert outputs["result_size"] == len("hello world")
    assert outputs["duration_ms"] >= 0
    assert "hello world" not in str(tracing.spans[0])


def test_run_never_raises_but_marks_the_span_failed() -> None:

    tracing = _FakeTracingService()
    tool = _EchoTool(tracing_service=tracing, fail=True)

    result = tool.run(operation="write", path="a.txt", content="x")

    assert result.success is False
    assert result.error == "disk is full"

    span = tracing.spans[0]
    assert span["outputs"]["success"] is False
    assert span["explicit_error"] == "disk is full"
    assert "error" not in span


def test_unknown_tool_name_falls_back_to_generic_category() -> None:
    class _MysteryTool(_EchoTool):
        @property
        def name(self) -> str:
            return "mystery"

    tracing = _FakeTracingService()
    tool = _MysteryTool(tracing_service=tracing)

    tool.run(operation="write", path="a.txt", content="x")

    assert tracing.spans[0]["metadata"]["tool_category"] == "tool"