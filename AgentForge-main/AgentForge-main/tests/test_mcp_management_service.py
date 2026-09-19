
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

import pytest

from backend.core.exceptions import MCPServerNotFoundError
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.registry import MCPToolRegistry
from backend.services.mcp_management_service import MCPHealthResult, MCPHealthStatus, MCPManagementService

TEST_SERVER_ARGS = ["-m", "tests.support.mcp_test_server"]


def _real_config(**overrides) -> MCPServerConfig:
    defaults = dict(
        name="test",
        display_name="Test Server",
        description="A real local test server.",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=TEST_SERVER_ARGS,
    )
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


def _service(configs: dict[str, MCPServerConfig]) -> MCPManagementService:
    return MCPManagementService(
        client_manager=MCPClientManager(configs),
        tool_registry=MCPToolRegistry(),
    )


def test_list_servers_reports_every_configured_server() -> None:
    service = _service({"a": _real_config(name="a"), "b": _real_config(name="b", enabled=False)})

    servers = service.list_servers()

    assert {s.id for s in servers} == {"a", "b"}


def test_disabled_server_reports_disabled_status() -> None:
    service = _service({"a": _real_config(name="a", enabled=False)})

    server = service.get_server("a")

    assert server.connection_status == MCPHealthStatus.DISABLED


def test_enabled_but_never_checked_server_reports_offline() -> None:
    service = _service({"a": _real_config(name="a")})

    server = service.get_server("a")

    assert server.connection_status == MCPHealthStatus.OFFLINE


def test_get_unknown_server_raises() -> None:
    service = _service({})

    with pytest.raises(MCPServerNotFoundError):
        service.get_server("nope")


def test_server_info_reports_display_name_description_and_auth() -> None:
    service = _service({"a": _real_config(name="a")})

    server = service.get_server("a")

    assert server.display_name == "Test Server"
    assert server.description == "A real local test server."
    assert server.auth_type == "none"
    assert server.auth_configured is False
    assert server.is_remote is False


def test_check_health_of_a_real_server_reports_online() -> None:
    service = _service({"test": _real_config()})

    result = asyncio.run(service.check_health("test"))

    assert result.status == MCPHealthStatus.ONLINE
    assert result.latency_ms is not None
    assert result.latency_ms >= 0

    server = service.get_server("test")
    assert server.connection_status == MCPHealthStatus.ONLINE
    assert server.latency_ms is not None


def test_check_health_of_a_disabled_server_reports_disabled_without_connecting() -> None:
    service = _service({"test": _real_config(enabled=False)})

    result = asyncio.run(service.check_health("test"))

    assert result.status == MCPHealthStatus.DISABLED


def test_check_health_of_an_unreachable_server_reports_unreachable() -> None:
    service = _service({"test": _real_config(command="this-command-does-not-exist-xyz", args=[])})

    result = asyncio.run(service.check_health("test"))

    assert result.status == MCPHealthStatus.UNREACHABLE
    assert result.error is not None


def test_check_all_health_only_checks_enabled_servers() -> None:
    service = _service(
        {
            "enabled_server": _real_config(name="enabled_server", enabled=True),
            "disabled_server": _real_config(name="disabled_server", enabled=False),
        }
    )

    results = asyncio.run(service.check_all_health())

    assert set(results) == {"enabled_server"}
    assert results["enabled_server"].status == MCPHealthStatus.ONLINE


def test_refresh_registry_discovers_tools_and_updates_tool_count() -> None:
    service = _service({"test": _real_config()})

    refreshed = asyncio.run(service.refresh_registry())

    assert refreshed == ["test"]
    server = service.get_server("test")
    assert server.tool_count == 3


def test_refresh_registry_skips_unreachable_servers_without_failing_others() -> None:
    service = _service(
        {
            "good": _real_config(name="good"),
            "bad": _real_config(name="bad", command="this-command-does-not-exist-xyz", args=[]),
        }
    )

    refreshed = asyncio.run(service.refresh_registry())

    assert refreshed == ["good"]


def test_list_tools_filters_by_query_after_refresh() -> None:
    service = _service({"test": _real_config()})
    asyncio.run(service.refresh_registry())

    matches = service.list_tools(query="echo")

    assert [t.tool_name for t in matches] == ["echo"]


def test_list_tools_filters_by_server() -> None:
    service = _service({"test": _real_config()})
    asyncio.run(service.refresh_registry())

    matches = service.list_tools(server_name="test")

    assert {t.tool_name for t in matches} == {"echo", "add", "get_test_document"}




def test_refresh_registry_skips_a_server_already_known_to_be_auth_failed() -> None:

    service = _service({"test": _real_config()})
    service._health_cache["test"] = MCPHealthResult(
        status=MCPHealthStatus.AUTH_FAILED, checked_at=datetime.now(UTC)
    )

    refreshed = asyncio.run(service.refresh_registry(skip_known_auth_failures=True))

    assert refreshed == []


def test_refresh_registry_without_the_flag_still_retries_auth_failures() -> None:
    service = _service({"test": _real_config()})
    service._health_cache["test"] = MCPHealthResult(
        status=MCPHealthStatus.AUTH_FAILED, checked_at=datetime.now(UTC)
    )

    refreshed = asyncio.run(service.refresh_registry())

    assert refreshed == ["test"]


def test_check_all_health_skips_a_server_already_known_to_be_auth_failed() -> None:
    service = _service({"test": _real_config()})
    stale = MCPHealthResult(status=MCPHealthStatus.AUTH_FAILED, checked_at=datetime.now(UTC))
    service._health_cache["test"] = stale

    results = asyncio.run(service.check_all_health(skip_known_auth_failures=True))

    assert results["test"] is stale
