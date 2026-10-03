
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

import httpx
from mcp.shared.exceptions import MCPError

from backend.core.exceptions import MCPConnectionError
from backend.mcp.cache import save_tool_cache
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPAuthType, MCPTransport
from backend.mcp.discovery import discover_tools
from backend.mcp.registry import MCPToolRegistry

logger = logging.getLogger(__name__)


class MCPHealthStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "authentication_failed"
    TIMEOUT = "timeout"
    DISABLED = "disabled"


@dataclass
class MCPHealthResult:
    status: MCPHealthStatus
    checked_at: datetime
    latency_ms: float | None = None
    version: str | None = None
    error: str | None = None


@dataclass
class MCPServerInfo:
    id: str
    display_name: str
    description: str | None
    transport: str
    is_remote: bool
    endpoint: str
    connection_status: MCPHealthStatus
    auth_type: str
    auth_configured: bool
    tool_count: int
    last_health_check: datetime | None
    version: str | None
    latency_ms: float | None


@dataclass
class MCPToolInfo:
    identity: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict


class MCPManagementService:
    def __init__(self, *, client_manager: MCPClientManager, tool_registry: MCPToolRegistry) -> None:
        self.client_manager = client_manager
        self.tool_registry = tool_registry
        self._health_cache: dict[str, MCPHealthResult] = {}


    def list_servers(self) -> list[MCPServerInfo]:
        return [self._server_info(name) for name in self.client_manager.all_server_names()]

    def get_server(self, server_name: str) -> MCPServerInfo:
        self.client_manager.config_for(server_name)
        return self._server_info(server_name)

    def _server_info(self, server_name: str) -> MCPServerInfo:
        config = self.client_manager.config_for(server_name)
        health = self._health_cache.get(server_name)

        if health is not None:
            status = health.status
        elif not config.enabled:
            status = MCPHealthStatus.DISABLED
        else:
            status = MCPHealthStatus.OFFLINE

        return MCPServerInfo(
            id=config.name,
            display_name=config.display_name or config.name,
            description=config.description,
            transport=config.transport.value,
            is_remote=config.transport == MCPTransport.HTTP,
            endpoint=config.url if config.transport == MCPTransport.HTTP else (config.command or ""),
            connection_status=status,
            auth_type=config.auth.type.value,
            auth_configured=config.auth.type != MCPAuthType.NONE and bool(config.auth.credential_env_var),
            tool_count=len(self.tool_registry.tools_for_server(server_name)),
            last_health_check=health.checked_at if health else None,
            version=health.version if health else None,
            latency_ms=health.latency_ms if health else None,
        )


    def list_tools(self, *, server_name: str | None = None, query: str | None = None) -> list[MCPToolInfo]:
        tools = (
            self.tool_registry.tools_for_server(server_name)
            if server_name is not None
            else self.tool_registry.all_tools()
        )

        if query:
            needle = query.lower()
            tools = [
                tool
                for tool in tools
                if needle in tool.tool_name.lower() or needle in tool.description.lower()
            ]

        return [
            MCPToolInfo(
                identity=tool.identity,
                server_name=tool.server_name,
                tool_name=tool.tool_name,
                description=tool.description,
                input_schema=tool.input_schema,
            )
            for tool in tools
        ]


    async def check_health(self, server_name: str) -> MCPHealthResult:
        config = self.client_manager.config_for(server_name)

        if not config.enabled:
            result = MCPHealthResult(status=MCPHealthStatus.DISABLED, checked_at=datetime.now(UTC))
            self._health_cache[server_name] = result
            return result

        started = time.monotonic()

        try:
            client = await asyncio.wait_for(
                self.client_manager.get_client(server_name), timeout=config.connection_timeout
            )
            try:
                await asyncio.wait_for(client.ping(), timeout=config.tool_timeout)
            except MCPError as error:
                if error.code != -32601:
                    raise
                await asyncio.wait_for(client.list_tools(), timeout=config.tool_timeout)

            version = None
            if client.initialize_result is not None and client.initialize_result.serverInfo is not None:
                version = client.initialize_result.serverInfo.version

            result = MCPHealthResult(
                status=MCPHealthStatus.ONLINE,
                checked_at=datetime.now(UTC),
                latency_ms=(time.monotonic() - started) * 1000,
                version=version,
            )
        except asyncio.TimeoutError:
            result = MCPHealthResult(status=MCPHealthStatus.TIMEOUT, checked_at=datetime.now(UTC))
        except httpx.HTTPStatusError as error:
            status = (
                MCPHealthStatus.AUTH_FAILED
                if error.response.status_code in (401, 403)
                else MCPHealthStatus.UNREACHABLE
            )
            result = MCPHealthResult(status=status, checked_at=datetime.now(UTC), error=str(error))
        except MCPConnectionError as error:
            result = MCPHealthResult(
                status=MCPHealthStatus.UNREACHABLE, checked_at=datetime.now(UTC), error=str(error)
            )
        except Exception as error:
            logger.warning("Health check failed for MCP server '%s'", server_name, exc_info=True)
            result = MCPHealthResult(
                status=MCPHealthStatus.UNREACHABLE, checked_at=datetime.now(UTC), error=str(error)
            )
        finally:
            # Stdio servers spawn a real subprocess on connect. Nothing keeps a
            # connection alive between health checks for any functional reason
            # (no agent is granted any of these servers today), so it's closed
            # immediately after each check rather than held open until the next
            # check interval -- holding N stdio subprocesses open indefinitely
            # is real, unbounded memory growth for zero benefit.
            if config.transport == MCPTransport.STDIO:
                await self.client_manager.close(server_name)

        self._health_cache[server_name] = result
        return result

    async def check_all_health(self, *, skip_known_auth_failures: bool = False) -> dict[str, MCPHealthResult]:
        for name in self.client_manager.enabled_server_names():
            if skip_known_auth_failures and self._is_known_auth_failure(name):
                continue

            await self.check_health(name)

        return dict(self._health_cache)

    def _is_known_auth_failure(self, server_name: str) -> bool:

        cached = self._health_cache.get(server_name)
        return cached is not None and cached.status == MCPHealthStatus.AUTH_FAILED


    async def refresh_registry(self, *, skip_known_auth_failures: bool = False) -> list[str]:

        refreshed: list[str] = []

        for name in self.client_manager.enabled_server_names():
            if skip_known_auth_failures and self._is_known_auth_failure(name):
                continue

            try:
                tools = await discover_tools(self.client_manager, name)
                self.tool_registry.unregister_server_tools(name)
                self.tool_registry.register_server_tools(name, tools)
                refreshed.append(name)
            except Exception:
                logger.warning("Failed to refresh MCP server '%s'", name, exc_info=True)
            finally:
                # Same reasoning as check_health(): close stdio subprocesses
                # immediately rather than leaving every enabled server's
                # process running simultaneously for the rest of this pass.
                if self.client_manager.config_for(name).transport == MCPTransport.STDIO:
                    await self.client_manager.close(name)

        if refreshed:
            save_tool_cache(self.tool_registry)

        return refreshed
