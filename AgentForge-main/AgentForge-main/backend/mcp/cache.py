
from __future__ import annotations

import json
import logging

from backend.core.workspace import REPOSITORY_ROOT
from backend.mcp.discovery import DiscoveredTool
from backend.mcp.registry import MCPToolRegistry

logger = logging.getLogger(__name__)

CACHE_PATH = REPOSITORY_ROOT / ".agentforge" / "mcp_tools_cache.json"


def save_tool_cache(registry: MCPToolRegistry) -> None:

    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tools": [tool.model_dump(mode="json") for tool in registry.all_tools()]}
        CACHE_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        logger.warning("Failed to write MCP tool discovery cache", exc_info=True)


def load_tool_cache() -> list[DiscoveredTool]:

    if not CACHE_PATH.exists():
        return []

    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

        return [DiscoveredTool.model_validate(entry) for entry in payload.get("tools", [])]
    except Exception:
        logger.warning("Failed to read MCP tool discovery cache; ignoring it.", exc_info=True)

        return []
