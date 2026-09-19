from __future__ import annotations

from pathlib import Path

import pytest

from backend.tools.filesystem_tool import FilesystemTool


@pytest.fixture
def tool(tmp_path: Path) -> FilesystemTool:
    return FilesystemTool(workspace=tmp_path)


def test_write_then_read_roundtrip(tool: FilesystemTool) -> None:
    write_result = tool.run(operation="write", path="a.txt", content="hello")
    assert write_result.success is True

    read_result = tool.run(operation="read", path="a.txt")
    assert read_result.success is True
    assert read_result.output == "hello"


def test_write_creates_parent_directories(tool: FilesystemTool) -> None:
    result = tool.run(
        operation="write",
        path="nested/dir/file.txt",
        content="x",
    )

    assert result.success is True


def test_read_missing_file_fails(tool: FilesystemTool) -> None:
    result = tool.run(operation="read", path="missing.txt")

    assert result.success is False


def test_read_rejects_directory(tool: FilesystemTool, tmp_path: Path) -> None:
    (tmp_path / "adir").mkdir()

    result = tool.run(operation="read", path="adir")

    assert result.success is False


def test_delete_rejects_directory(tool: FilesystemTool, tmp_path: Path) -> None:
    (tmp_path / "adir").mkdir()

    result = tool.run(operation="delete", path="adir")

    assert result.success is False


def test_relative_path_traversal_is_blocked(tool: FilesystemTool) -> None:
    result = tool.run(operation="write", path="../outside.txt", content="x")

    assert result.success is False
    assert "workspace" in (result.error or "").lower()


def test_absolute_path_outside_workspace_is_blocked(
    tool: FilesystemTool, tmp_path: Path
) -> None:
    outside = tmp_path.parent / "outside.txt"

    result = tool.run(operation="write", path=str(outside), content="x")

    assert result.success is False


def test_workspace_root_cannot_be_deleted(
    tool: FilesystemTool, tmp_path: Path
) -> None:
    result = tool.run(operation="delete", path=str(tmp_path))

    assert result.success is False


def test_list_directory_is_sorted(tool: FilesystemTool) -> None:
    tool.run(operation="write", path="b.txt", content="1")
    tool.run(operation="write", path="a.txt", content="2")

    result = tool.run(operation="list", path=".")

    assert result.success is True
    assert result.output == sorted(result.output)


def test_symlink_escape_is_blocked(tool: FilesystemTool, tmp_path: Path) -> None:

    outside_dir = tmp_path.parent / f"outside-{tmp_path.name}"
    outside_dir.mkdir(exist_ok=True)
    outside_target = outside_dir / "secret.txt"
    outside_target.write_text("secret", encoding="utf-8")

    link_path = tmp_path / "escape_link"

    try:
        link_path.symlink_to(outside_target)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted in this environment.")

    result = tool.run(operation="read", path="escape_link")

    assert result.success is False


def test_appending_beyond_symlink_directory_is_blocked(
    tool: FilesystemTool, tmp_path: Path
) -> None:
    outside_dir = tmp_path.parent / f"outside2-{tmp_path.name}"
    outside_dir.mkdir(exist_ok=True)

    link_dir = tmp_path / "escape_dir"

    try:
        link_dir.symlink_to(outside_dir, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not permitted in this environment.")

    result = tool.run(
        operation="write",
        path="escape_dir/pwned.txt",
        content="x",
    )

    assert result.success is False
    assert not (outside_dir / "pwned.txt").exists()


def test_cannot_write_into_agentforge_source_tree() -> None:

    from backend.core.workspace import REPOSITORY_ROOT

    misconfigured_tool = FilesystemTool(workspace=REPOSITORY_ROOT)

    result = misconfigured_tool.run(
        operation="write",
        path="backend/should_not_write.py",
        content="x",
    )

    assert result.success is False
