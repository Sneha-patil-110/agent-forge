
from __future__ import annotations

import sys

import pytest

from backend.core.constants import MAX_MCP_RESULT_CHARS
from backend.core.exceptions import (
    MCPPermissionDeniedError,
    MCPToolExecutionError,
    MCPToolNotFoundError,
)
from backend.core.workspace import REPOSITORY_ROOT
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.discovery import discover_tools
from backend.mcp.executor import MCPToolExecutor, get_current_run_id, set_current_run_id
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.state.execution_state import AgentType

RUN_ID = "af_20260715_deadbeef"


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


def test_authorized_call_returns_bounded_result(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    result = executor.execute(
        agent=AgentType.DOCUMENTATION,
        tool_identity="test.add",
        arguments={"a": 2, "b": 3},
    )

    assert result.success is True
    assert result.data == "5"
    assert result.truncated is False


def test_local_filesystem_path_redacted_from_tool_result(real_setup) -> None:

    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    leaky_message = f"Parent directory does not exist: {REPOSITORY_ROOT}\\workspace\\backend\\tests"

    result = executor.execute(
        agent=AgentType.DOCUMENTATION,
        tool_identity="test.echo",
        arguments={"message": leaky_message},
    )

    assert str(REPOSITORY_ROOT) not in result.data
    assert "<agentforge>" in result.data
    assert result.data.endswith("workspace\\backend\\tests")


def test_unauthorized_call_rejected(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy()
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    with pytest.raises(MCPPermissionDeniedError):
        executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.add", arguments={"a": 1, "b": 2})


def test_unknown_tool_rejected(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    with pytest.raises(MCPToolNotFoundError):
        executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.does_not_exist", arguments={})


def test_invalid_arguments_rejected_by_fastmcp_validation(real_setup) -> None:

    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    with pytest.raises(MCPToolExecutionError):
        executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.add", arguments={"a": 1})


def test_permission_checked_before_tool_resolution_failure_is_still_correct(real_setup) -> None:

    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.echo"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    result = executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": "hi"})
    assert result.data == "hi"

    with pytest.raises(MCPPermissionDeniedError):
        executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.add", arguments={"a": 1, "b": 2})


def test_result_truncated_when_oversized(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    huge_topic = "x" * (MAX_MCP_RESULT_CHARS + 500)
    result = executor.execute(
        agent=AgentType.DOCUMENTATION, tool_identity="test.get_test_document", arguments={"topic": huge_topic}
    )

    assert result.truncated is True
    assert len(result.data) < len(huge_topic)
    assert "truncated" in result.data


def test_empty_string_result_handled_safely(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    executor = MCPToolExecutor(client_manager=manager, registry=registry, permission_policy=policy)
    set_current_run_id(RUN_ID)

    result = executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": ""})

    assert result.success is True
    assert result.data == ""


def test_events_emitted_for_successful_call(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    dispatcher = EventDispatcher()
    events = []
    dispatcher.subscribe(events.append)
    executor = MCPToolExecutor(
        client_manager=manager, registry=registry, permission_policy=policy, event_dispatcher=dispatcher
    )
    set_current_run_id(RUN_ID)

    executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": "hi"})

    assert [e.event_type for e in events] == [
        EventType.MCP_TOOL_CALL_STARTED,
        EventType.MCP_TOOL_CALL_COMPLETED,
        EventType.MCP_TOOL_CALL_RECORDED,
    ]
    assert all(e.run_id == RUN_ID for e in events)

    started_and_completed = [e for e in events if e.event_type != EventType.MCP_TOOL_CALL_RECORDED]
    assert all(e.metadata == {"tool": "test.echo"} for e in started_and_completed)

    recorded = events[-1]
    assert recorded.metadata["server_name"] == "test"
    assert recorded.metadata["tool_name"] == "echo"
    assert recorded.metadata["success"] is True


def test_events_never_contain_arguments_or_results(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    dispatcher = EventDispatcher()
    events = []
    dispatcher.subscribe(events.append)
    executor = MCPToolExecutor(
        client_manager=manager, registry=registry, permission_policy=policy, event_dispatcher=dispatcher
    )
    set_current_run_id(RUN_ID)

    secret_marker = "super-secret-argument-value"
    executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": secret_marker})

    serialized = "\n".join(e.model_dump_json() for e in events)
    assert secret_marker not in serialized


def test_no_event_emitted_when_run_id_not_set(real_setup) -> None:
    manager, registry = real_setup
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"test.*"})})
    dispatcher = EventDispatcher()
    events = []
    dispatcher.subscribe(events.append)
    executor = MCPToolExecutor(
        client_manager=manager, registry=registry, permission_policy=policy, event_dispatcher=dispatcher
    )

    executor.execute(agent=AgentType.DOCUMENTATION, tool_identity="test.echo", arguments={"message": "hi"})

    assert events == []


def test_get_current_run_id_reflects_set_value() -> None:
    assert get_current_run_id() is None
    set_current_run_id("af_20260715_deadbeef")
    assert get_current_run_id() == "af_20260715_deadbeef"
