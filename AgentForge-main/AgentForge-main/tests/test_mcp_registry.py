from __future__ import annotations

import pytest

from backend.core.exceptions import MCPDuplicateToolError, MCPToolNotFoundError
from backend.mcp.discovery import DiscoveredTool
from backend.mcp.registry import MCPToolRegistry


def _tool(server: str, name: str) -> DiscoveredTool:
    return DiscoveredTool(
        identity=f"{server}.{name}",
        server_name=server,
        tool_name=name,
        description="d",
        input_schema={"type": "object", "properties": {}},
    )


def test_register_and_lookup() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search")])

    assert registry.has("docs.search")
    assert registry.get("docs.search").tool_name == "search"


def test_unknown_tool_raises() -> None:
    registry = MCPToolRegistry()

    with pytest.raises(MCPToolNotFoundError):
        registry.get("nope.nope")


def test_registering_same_tool_from_same_server_twice_is_idempotent() -> None:
    registry = MCPToolRegistry()
    tool = _tool("docs", "search")

    registry.register_server_tools("docs", [tool])
    registry.register_server_tools("docs", [tool])

    assert len(registry) == 1


def test_duplicate_identity_from_different_server_raises() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search")])

    colliding = DiscoveredTool(
        identity="docs.search",
        server_name="other",
        tool_name="search",
        description="d",
        input_schema={},
    )

    with pytest.raises(MCPDuplicateToolError):
        registry.register_server_tools("other", [colliding])

    assert registry.get("docs.search").server_name == "docs"


def test_tools_for_server_filters_correctly() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search"), _tool("docs", "fetch")])
    registry.register_server_tools("github", [_tool("github", "search")])

    docs_tools = {t.identity for t in registry.tools_for_server("docs")}
    assert docs_tools == {"docs.search", "docs.fetch"}


def test_all_tools_and_len_and_contains() -> None:
    registry = MCPToolRegistry()
    assert len(registry) == 0
    assert "docs.search" not in registry

    registry.register_server_tools("docs", [_tool("docs", "search")])

    assert len(registry) == 1
    assert "docs.search" in registry
    assert len(registry.all_tools()) == 1


def test_clear_empties_registry() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search")])
    registry.clear()

    assert len(registry) == 0


def test_unregister_server_tools_removes_only_that_servers_tools() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search"), _tool("docs", "fetch")])
    registry.register_server_tools("github", [_tool("github", "search")])

    registry.unregister_server_tools("docs")

    assert registry.tools_for_server("docs") == ()
    assert registry.has("github.search")
    assert len(registry) == 1


def test_unregister_then_reregister_drops_stale_tools() -> None:

    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search"), _tool("docs", "fetch")])

    registry.unregister_server_tools("docs")
    registry.register_server_tools("docs", [_tool("docs", "search")])

    assert {t.identity for t in registry.tools_for_server("docs")} == {"docs.search"}


def test_unregister_unknown_server_is_a_safe_no_op() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search")])

    registry.unregister_server_tools("does-not-exist")

    assert len(registry) == 1
