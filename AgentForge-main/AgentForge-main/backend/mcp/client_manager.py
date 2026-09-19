from __future__ import annotations

import logging
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from backend.core.exceptions import MCPConnectionError, MCPServerNotFoundError
from backend.core.logging import LOG_DIR
from backend.mcp.config import MCPServerConfig, MCPTransport
from backend.mcp.metrics import MCPMetricsCollector

logger = logging.getLogger(__name__)

MCP_STDERR_DIR = LOG_DIR / "mcp"
MCP_STDERR_DIR.mkdir(parents=True, exist_ok=True)

_STDERR_TAIL_CHARS = 4000


def _stderr_log_path(server_name: str) -> Path:
    return MCP_STDERR_DIR / f"{server_name}.stderr.log"


def _read_stderr_tail(server_name: str) -> str:
    path = _stderr_log_path(server_name)

    if not path.exists():
        return ""

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""

    return text[-_STDERR_TAIL_CHARS:].strip()


def _build_transport(config: MCPServerConfig):
    if config.transport == MCPTransport.STDIO:
        return StdioTransport(
            command=config.command,
            args=config.args,
            env=config.resolved_env() or None,
            log_file=_stderr_log_path(config.name),
        )

    return StreamableHttpTransport(url=config.url, headers=config.resolved_auth_headers() or None)


class MCPClientManager:

    def __init__(
        self,
        configs: dict[str, MCPServerConfig],
        *,
        metrics: MCPMetricsCollector | None = None,
    ) -> None:
        self._configs = configs
        self._clients: dict[str, Client] = {}
        self.metrics = metrics or MCPMetricsCollector()

    def is_enabled(self, server_name: str) -> bool:
        config = self._configs.get(server_name)
        return config is not None and config.enabled

    def config_for(self, server_name: str) -> MCPServerConfig:
        config = self._configs.get(server_name)

        if config is None:
            raise MCPServerNotFoundError(
                f"MCP server '{server_name}' is not configured.",
                details={"server": server_name},
            )

        return config

    def enabled_server_names(self) -> list[str]:
        return sorted(
            name for name, config in self._configs.items() if config.enabled
        )

    def all_server_names(self) -> list[str]:
        return sorted(self._configs.keys())

    def is_connected(self, server_name: str) -> bool:
        client = self._clients.get(server_name)
        return client is not None and client.is_connected()

    def connected_client(self, server_name: str) -> Client | None:

        client = self._clients.get(server_name)
        return client if client is not None and client.is_connected() else None

    async def get_client(self, server_name: str) -> Client:
        config = self._configs.get(server_name)

        if config is None or not config.enabled:
            raise MCPServerNotFoundError(
                f"MCP server '{server_name}' is not configured or not enabled.",
                details={"server": server_name},
            )

        client = self._clients.get(server_name)

        if client is not None and client.is_connected():
            return client

        if config.transport == MCPTransport.STDIO:
            _stderr_log_path(server_name).write_text("", encoding="utf-8")

        transport = _build_transport(config)
        client = Client(transport, timeout=config.connection_timeout)

        try:
            await client.__aenter__()
        except Exception as error:
            message = f"Failed to connect to MCP server '{server_name}': {error}"
            stderr_tail = _read_stderr_tail(server_name) if config.transport == MCPTransport.STDIO else ""

            if stderr_tail:
                message = f"{message}\n--- subprocess stderr ---\n{stderr_tail}"

            raise MCPConnectionError(message, details={"server": server_name}) from error

        self._clients[server_name] = client
        self.metrics.record_connected(server_name)
        logger.info("Connected to MCP server '%s'", server_name)

        return client

    async def close(self, server_name: str) -> None:

        client = self._clients.pop(server_name, None)

        if client is None:
            return

        try:
            if client.is_connected():
                await client.__aexit__(None, None, None)
        except Exception:
            logger.exception("Error closing MCP server '%s'", server_name)

    async def close_all(self) -> None:
        for server_name, client in list(self._clients.items()):
            try:
                if client.is_connected():
                    await client.__aexit__(None, None, None)
            except Exception:
                logger.exception("Error closing MCP server '%s'", server_name)

        self._clients.clear()
