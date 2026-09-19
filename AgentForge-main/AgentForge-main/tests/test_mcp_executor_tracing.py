from __future__ import annotations

import sys
from contextlib import contextmanager

import pytest

from backend.core.exceptions import MCPPermissionDeniedError
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.discovery import discover_tools
from backend.mcp.executor import MCPToolExecutor, set_current_run_id
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.state.execution_state import AgentType

RUN_ID = "af_20260716_deadbeef"


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


@pytest.fixture
def real_setup():
    config = MCPServerConfig(
        name="test",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=["-m", "tests.support.mcp_test_server"],
    )
    manager = MCPClientManager({"test": config})
    registry = MCPToolRegistry()

    import asyncio

    tools = asyncio.run(discover_tools(manager, "test"))
    registry.register_server_tools("test", tools)

    yield manager, registry

    asyncio.run(manager.close_all())


@pytest.fixture(autouse=True)
def _reset_run_id():
    set_current_run_id(None)
    yield
    set_current_run_id(None)


def test_successful_call_opens_a_span_with_server_tool_and_agent_metadata(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    tracing = _FakeTracingService()
    executor = MCPToolExecutor(
        client_manager=manager, registry=registry, permission_policy=policy, tracing_service=tracing
    )
    set_current_run_id(RUN_ID)

    executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": "hi"})

    assert len(tracing.spans) == 1
    span = tracing.spans[0]
    assert span["name"] == "mcp:test.echo"
    assert span["run_type"] == "tool"
    assert "mcp_server:test" in span["tags"]
    assert span["metadata"]["mcp_server"] == "test"
    assert span["metadata"]["mcp_tool"] == "echo"
    assert span["metadata"]["agent"] == AgentType.DOCUMENTATION.value
    assert span["outputs"]["success"] is True
    assert span["outputs"]["duration_ms"] >= 0


def test_permission_denied_is_visible_on_the_span_without_swallowing_the_error(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy()
    tracing = _FakeTracingService()
    executor = MCPToolExecutor(
        client_manager=manager, registry=registry, permission_policy=policy, tracing_service=tracing
    )
    set_current_run_id(RUN_ID)

    with pytest.raises(MCPPermissionDeniedError):
        executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.add", arguments={"a": 1, "b": 2})

    assert len(tracing.spans) == 1
    assert "MCPPermissionDeniedError" in tracing.spans[0]["error"]
    assert "outputs" not in tracing.spans[0]


def test_without_a_tracing_service_behaves_exactly_as_before(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    result = executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": "hi"})

    assert result.success is True
    assert result.data == "hi"