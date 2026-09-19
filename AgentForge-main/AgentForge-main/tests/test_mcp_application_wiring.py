from __future__ import annotations

from backend.core.app import Application
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.executor import MCPToolExecutor
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.state.execution_state import AgentType


def test_application_wires_mcp_subsystem() -> None:
    application = Application()

    assert isinstance(application.mcp_client_manager, MCPClientManager)
    assert isinstance(application.mcp_tool_registry, MCPToolRegistry)
    assert isinstance(application.mcp_permission_policy, MCPPermissionPolicy)
    assert isinstance(application.mcp_tool_executor, MCPToolExecutor)

    application.shutdown()


def test_no_servers_configured_is_fully_inert(monkeypatch) -> None:
    monkeypatch.setattr("backend.core.app.load_mcp_server_configs", lambda: {})

    application = Application()

    assert application.mcp_client_manager.enabled_server_names() == []
    assert len(application.mcp_tool_registry) == 0
    assert application.documentation_agent.mcp_tool_identities == []

    application.shutdown()


def test_shipped_config_includes_the_local_tools_demo_server() -> None:

    application = Application()

    assert "local-tools" in application.mcp_client_manager.enabled_server_names()
    assert all(
        not identity.startswith("local-tools.")
        for identity in application.documentation_agent.mcp_tool_identities
    )

    application.shutdown()


def test_every_agent_receives_mcp_kwargs() -> None:

    application = Application()

    for agent, agent_type in (
        (application.analysis_agent, AgentType.ANALYSIS),
        (application.planner_agent, AgentType.PLANNER),
        (application.architect_agent, AgentType.ARCHITECT),
        (application.developer_agent, AgentType.DEVELOPER),
        (application.tester_agent, AgentType.TESTER),
        (application.debugger_agent, AgentType.DEBUGGER),
        (application.reviewer_agent, AgentType.REVIEWER),
        (application.documentation_agent, AgentType.DOCUMENTATION),
    ):
        assert agent.mcp_executor is application.mcp_tool_executor
        assert agent.mcp_registry is application.mcp_tool_registry
        assert agent.mcp_tool_identities == application.mcp_permission_policy.allowed_identities(
            agent_type, application.mcp_tool_registry
        )

    application.shutdown()


def test_shutdown_is_safe_to_call_with_no_open_connections() -> None:
    application = Application()
    application.shutdown()
    application.shutdown()
