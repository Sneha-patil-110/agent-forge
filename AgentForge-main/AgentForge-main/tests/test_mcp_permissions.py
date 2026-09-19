from __future__ import annotations

from backend.mcp.discovery import DiscoveredTool
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.state.execution_state import AgentType


def _tool(server: str, name: str) -> DiscoveredTool:
    return DiscoveredTool(
        identity=f"{server}.{name}", server_name=server, tool_name=name, description="d"
    )


def test_deny_by_default() -> None:
    policy = MCPPermissionPolicy()

    assert policy.is_authorized(AgentType.DOCUMENTATION, "docs.search") is False


def test_exact_identity_allowed() -> None:
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"docs.search"})})

    assert policy.is_authorized(AgentType.DOCUMENTATION, "docs.search") is True
    assert policy.is_authorized(AgentType.DOCUMENTATION, "docs.fetch") is False


def test_server_wildcard_allows_every_tool_from_that_server() -> None:
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"docs.*"})})

    assert policy.is_authorized(AgentType.DOCUMENTATION, "docs.search") is True
    assert policy.is_authorized(AgentType.DOCUMENTATION, "docs.fetch") is True
    assert policy.is_authorized(AgentType.DOCUMENTATION, "github.search") is False


def test_wildcard_does_not_leak_to_other_agents() -> None:
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"docs.*"})})

    assert policy.is_authorized(AgentType.DEVELOPER, "docs.search") is False


def test_llm_cannot_self_grant_permission_via_unmapped_agent() -> None:

    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"docs.*"})})

    for agent in AgentType:
        if agent != AgentType.DOCUMENTATION:
            assert policy.is_authorized(agent, "docs.search") is False


def test_allowed_identities_resolves_against_registry() -> None:
    registry = MCPToolRegistry()
    registry.register_server_tools("docs", [_tool("docs", "search"), _tool("docs", "fetch")])
    registry.register_server_tools("github", [_tool("github", "search")])

    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"docs.*"})})

    identities = set(policy.allowed_identities(AgentType.DOCUMENTATION, registry))
    assert identities == {"docs.search", "docs.fetch"}


def test_allowed_identities_empty_when_nothing_registered() -> None:
    registry = MCPToolRegistry()
    policy = MCPPermissionPolicy({AgentType.DOCUMENTATION: frozenset({"docs.*"})})

    assert policy.allowed_identities(AgentType.DOCUMENTATION, registry) == []
