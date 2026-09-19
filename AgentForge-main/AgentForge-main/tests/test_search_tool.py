from __future__ import annotations

from pathlib import Path

import pytest

from backend.tools.search_tool import SearchTool


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "src" / "utils.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Project\n\nhello world\n", encoding="utf-8")

    ignored_dir = tmp_path / "node_modules"
    ignored_dir.mkdir()
    (ignored_dir / "lib.js").write_text("hello", encoding="utf-8")

    binary_dir = tmp_path / "assets"
    binary_dir.mkdir()
    (binary_dir / "image.bin").write_bytes(bytes(range(256)))

    return tmp_path


@pytest.fixture
def tool(workspace: Path) -> SearchTool:
    return SearchTool(workspace=workspace)


def test_find_files_by_glob_pattern(tool: SearchTool) -> None:
    result = tool.run(operation="files", pattern="*.py")

    assert result.success is True
    assert set(result.output) == {"src/app.py", "src/utils.py"}


def test_find_files_ignores_configured_directories(tool: SearchTool) -> None:
    result = tool.run(operation="files", pattern="*")

    assert result.success is True
    assert not any("node_modules" in path for path in result.output)


def test_search_text_finds_matches_across_files(tool: SearchTool) -> None:
    result = tool.run(operation="text", query="hello")

    assert result.success is True
    files_matched = {match["file"] for match in result.output}
    assert "src/app.py" in files_matched
    assert "README.md" in files_matched
    assert not any("node_modules" in f for f in files_matched)


def test_search_text_is_case_insensitive_by_default(tool: SearchTool) -> None:
    result = tool.run(operation="text", query="HELLO")

    assert result.success is True
    assert len(result.output) > 0


def test_search_text_case_sensitive_option(tool: SearchTool) -> None:
    result = tool.run(operation="text", query="HELLO", case_sensitive=True)

    assert result.success is True
    assert result.output == []


def test_search_text_skips_unreadable_binary_files(tool: SearchTool) -> None:
    result = tool.run(operation="text", query="hello")

    assert result.success is True
    assert not any("image.bin" in match["file"] for match in result.output)


def test_missing_root_raises_error(tool: SearchTool) -> None:
    result = tool.run(operation="files", root="does-not-exist", pattern="*")

    assert result.success is False


def test_root_outside_workspace_is_blocked(tool: SearchTool, workspace: Path) -> None:
    result = tool.run(
        operation="files",
        root=str(workspace.parent),
        pattern="*",
    )

    assert result.success is False


def test_max_results_limits_output(tool: SearchTool) -> None:
    result = tool.run(operation="files", pattern="*.py", max_results=1)

    assert result.success is True
    assert len(result.output) == 1


def test_find_files_results_are_sorted() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "b.py").write_text("", encoding="utf-8")
        (tmp_path / "a.py").write_text("", encoding="utf-8")

        tool = SearchTool(workspace=tmp_path)
        result = tool.run(operation="files", pattern="*.py")

        assert result.output == sorted(result.output)
