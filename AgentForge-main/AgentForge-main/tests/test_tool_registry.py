from __future__ import annotations

import pytest

from backend.core.exceptions import ToolError
from backend.tools.tool_registry import ToolRegistry
from backend.tools.filesystem_tool import FilesystemTool


def test_register_and_get() -> None:
    registry = ToolRegistry()
    tool = FilesystemTool()

    registry.register(tool)

    assert registry.get("filesystem") is tool


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool())

    with pytest.raises(ToolError):
        registry.register(FilesystemTool())


def test_get_missing_tool_raises() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolError):
        registry.get("does-not-exist")


def test_tool_names_are_sorted() -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool())

    assert registry.tool_names() == sorted(registry.tool_names())


def test_all_tools_is_immutable_tuple() -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool())

    tools = registry.all_tools()

    assert isinstance(tools, tuple)


def test_describe_tools_lists_registered_tools() -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool())

    description = registry.describe_tools()

    assert "filesystem" in description


def test_unregister_removes_tool() -> None:
    registry = ToolRegistry()
    registry.register(FilesystemTool())

    registry.unregister("filesystem")

    assert "filesystem" not in registry
    with pytest.raises(ToolError):
        registry.get("filesystem")


def test_unregister_missing_tool_raises() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolError):
        registry.unregister("does-not-exist")


def test_register_rejects_non_tool_instance() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolError):
        registry.register(object())


def test_contains_and_len() -> None:
    registry = ToolRegistry()

    assert "filesystem" not in registry
    assert len(registry) == 0

    registry.register(FilesystemTool())

    assert "filesystem" in registry
    assert len(registry) == 1
