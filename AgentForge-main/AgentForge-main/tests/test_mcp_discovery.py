from __future__ import annotations

import asyncio
import sys

from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.discovery import discover_tools


def _manager() -> MCPClientManager:
    config = MCPServerConfig(
        name="test",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=["-m", "tests.support.mcp_test_server"],
    )
    return MCPClientManager({"test": config})


def test_discovers_real_tools_with_namespaced_identity() -> None:
    manager = _manager()

    async def scenario():
        tools = await discover_tools(manager, "test")
        await manager.close_all()
        return tools

    tools = asyncio.run(scenario())

    identities = {t.identity for t in tools}
    assert identities == {"test.echo", "test.add", "test.get_test_document"}
    assert all(t.server_name == "test" for t in tools)


def test_discovered_tool_carries_schema_and_description() -> None:
    manager = _manager()

    async def scenario():
        tools = await discover_tools(manager, "test")
        await manager.close_all()
        return tools

    tools = asyncio.run(scenario())
    add_tool = next(t for t in tools if t.tool_name == "add")

    assert add_tool.description
    assert add_tool.input_schema["properties"]["a"]["type"] == "integer"
    assert add_tool.input_schema["properties"]["b"]["type"] == "integer"


def test_as_langchain_tool_schema_shape() -> None:
    manager = _manager()

    async def scenario():
        tools = await discover_tools(manager, "test")
        await manager.close_all()
        return tools

    tools = asyncio.run(scenario())
    echo_tool = next(t for t in tools if t.tool_name == "echo")
    schema = echo_tool.as_langchain_tool_schema()

    assert schema["type"] == "function"
    assert schema["function"]["name"] == "test__echo"
    assert echo_tool.llm_name == "test__echo"
    assert schema["function"]["parameters"] == echo_tool.input_schema
