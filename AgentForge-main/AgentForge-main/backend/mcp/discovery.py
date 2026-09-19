from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from backend.mcp.client_manager import MCPClientManager

_UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")


class DiscoveredTool(BaseModel):
    model_config = ConfigDict(frozen=True)

    identity: str = Field(..., description="Namespaced identity: '<server>.<tool>'.")
    server_name: str
    tool_name: str
    description: str = ""
    input_schema: dict = Field(default_factory=dict)

    @property
    def llm_name(self) -> str:

        return _UNSAFE_NAME_CHARS.sub("_", self.identity.replace(".", "__"))

    def as_langchain_tool_schema(self) -> dict:

        return {
            "type": "function",
            "function": {
                "name": self.llm_name,
                "description": self.description,
                "parameters": self.input_schema or {"type": "object", "properties": {}},
            },
        }


async def discover_tools(
    client_manager: MCPClientManager,
    server_name: str,
) -> list[DiscoveredTool]:
    client = await client_manager.get_client(server_name)
    tools = await client.list_tools()

    return [
        DiscoveredTool(
            identity=f"{server_name}.{tool.name}",
            server_name=server_name,
            tool_name=tool.name,
            description=tool.description or "",
            input_schema=tool.inputSchema or {},
        )
        for tool in tools
    ]
