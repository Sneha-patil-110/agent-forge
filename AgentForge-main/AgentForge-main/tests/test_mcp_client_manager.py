
from __future__ import annotations

import asyncio
import sys

import pytest

from backend.core.exceptions import MCPConnectionError, MCPServerNotFoundError
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport

TEST_SERVER_ARGS = ["-m", "tests.support.mcp_test_server"]


def _real_config(**overrides) -> MCPServerConfig:
    defaults = dict(
        name="test",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=TEST_SERVER_ARGS,
    )
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


def test_connects_to_real_local_server_and_lists_tools() -> None:
    manager = MCPClientManager({"test": _real_config()})

    async def scenario():
        client = await manager.get_client("test")
        tools = await client.list_tools()
        assert {t.name for t in tools} == {"echo", "add", "get_test_document"}
        await manager.close_all()

    asyncio.run(scenario())


def test_reuses_same_client_within_one_event_loop() -> None:
    manager = MCPClientManager({"test": _real_config()})

    async def scenario():
        client_a = await manager.get_client("test")
        client_b = await manager.get_client("test")
        assert client_a is client_b
        await manager.close_all()

    asyncio.run(scenario())


def test_disabled_server_rejected() -> None:
    manager = MCPClientManager({"test": _real_config(enabled=False)})

    async def scenario():
        await manager.get_client("test")

    with pytest.raises(MCPServerNotFoundError):
        asyncio.run(scenario())


def test_unconfigured_server_rejected() -> None:
    manager = MCPClientManager({})

    async def scenario():
        await manager.get_client("does-not-exist")

    with pytest.raises(MCPServerNotFoundError):
        asyncio.run(scenario())


def test_connection_failure_raises_mcp_connection_error() -> None:
    config = _real_config(command="this-command-does-not-exist-xyz", args=[])
    manager = MCPClientManager({"test": config})

    async def scenario():
        await manager.get_client("test")

    with pytest.raises(MCPConnectionError):
        asyncio.run(scenario())


def test_close_all_is_clean_and_idempotent() -> None:
    manager = MCPClientManager({"test": _real_config()})

    async def scenario():
        await manager.get_client("test")
        await manager.close_all()
        await manager.close_all()

    asyncio.run(scenario())


def test_enabled_server_names_reflects_config() -> None:
    manager = MCPClientManager(
        {
            "a": _real_config(name="a", enabled=True),
            "b": _real_config(name="b", enabled=False),
        }
    )

    assert manager.enabled_server_names() == ["a"]


def test_config_for_unknown_server_raises() -> None:
    manager = MCPClientManager({})

    with pytest.raises(MCPServerNotFoundError):
        manager.config_for("nope")
