from __future__ import annotations

from backend.core.exceptions import MCPDuplicateToolError, MCPToolNotFoundError
from backend.mcp.discovery import DiscoveredTool


class MCPToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, DiscoveredTool] = {}

    def register_server_tools(self, server_name: str, tools: list[DiscoveredTool]) -> None:
        for tool in tools:
            if tool.identity in self._tools:
                existing = self._tools[tool.identity]

                if existing.server_name != tool.server_name:
                    raise MCPDuplicateToolError(
                        f"Tool identity '{tool.identity}' is already registered "
                        f"by server '{existing.server_name}'.",
                        details={"identity": tool.identity},
                    )

                continue

            self._tools[tool.identity] = tool

    def get(self, identity: str) -> DiscoveredTool:
        tool = self._tools.get(identity)

        if tool is None:
            raise MCPToolNotFoundError(
                f"MCP tool '{identity}' is not registered.",
                details={"identity": identity},
            )

        return tool

    def has(self, identity: str) -> bool:
        return identity in self._tools

    def all_tools(self) -> tuple[DiscoveredTool, ...]:
        return tuple(self._tools.values())

    def tools_for_server(self, server_name: str) -> tuple[DiscoveredTool, ...]:
        return tuple(
            tool for tool in self._tools.values() if tool.server_name == server_name
        )

    def unregister_server_tools(self, server_name: str) -> None:

        for identity in [
            identity for identity, tool in self._tools.items() if tool.server_name == server_name
        ]:
            del self._tools[identity]

    def clear(self) -> None:
        self._tools.clear()

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, identity: str) -> bool:
        return self.has(identity)
