from __future__ import annotations

from backend.core.exceptions import ToolError
from backend.tools.base_tool import BaseTool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(
        self,
        tool: BaseTool,
    ) -> None:
        if not isinstance(tool, BaseTool):
            raise ToolError(
                "Only BaseTool instances can be registered."
            )

        if tool.name in self._tools:
            raise ToolError(
                f"Tool '{tool.name}' is already registered."
            )

        self._tools[tool.name] = tool

    def get(
        self,
        name: str,
    ) -> BaseTool:
        tool = self._tools.get(name)

        if tool is None:
            available_tools = ", ".join(
                self.tool_names()
            ) or "none"

            raise ToolError(
                f"Tool '{name}' is not registered. "
                f"Available tools: {available_tools}."
            )

        return tool

    def has(
        self,
        name: str,
    ) -> bool:
        return name in self._tools

    def unregister(
        self,
        name: str,
    ) -> None:
        if not self.has(name):
            raise ToolError(
                f"Tool '{name}' is not registered."
            )

        del self._tools[name]

    def all_tools(
        self,
    ) -> tuple[BaseTool, ...]:
        return tuple(self._tools.values())

    def tool_names(
        self,
    ) -> list[str]:
        return sorted(self._tools.keys())

    def describe_tools(
        self,
    ) -> str:
        if not self._tools:
            return "No tools are currently registered."

        descriptions: list[str] = []

        for tool in self.all_tools():
            description = getattr(
                tool,
                "description",
                "No description available.",
            )

            descriptions.append(
                f"{tool.name}: {description}"
            )

        return "\n".join(descriptions)

    def clear(
        self,
    ) -> None:
        self._tools.clear()

    def __len__(
        self,
    ) -> int:
        return len(self._tools)

    def __contains__(
        self,
        name: str,
    ) -> bool:
        return self.has(name)
