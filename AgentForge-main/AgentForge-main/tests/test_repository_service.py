from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.core.exceptions import InvalidRepositoryPathError
from backend.events.dispatcher import EventDispatcher
from backend.services.repository_service import RepositoryService
from backend.tools.filesystem_tool import FilesystemTool
from backend.tools.tool_registry import ToolRegistry


@pytest.fixture
def service(tmp_path: Path) -> RepositoryService:
    registry = ToolRegistry()
    registry.register(FilesystemTool(workspace=tmp_path))
    return RepositoryService(tool_registry=registry, event_dispatcher=EventDispatcher(), db_session_factory=None)


def _make_run_dir(tmp_path: Path) -> Path:
    output_directory = tmp_path / "af_20260718_symlink0"
    output_directory.mkdir()
    return output_directory


def _can_create_symlinks(tmp_path: Path) -> bool:
    target = tmp_path / "_symlink_probe_target"
    link = tmp_path / "_symlink_probe_link"
    target.write_text("probe")
    try:
        os.symlink(str(target), str(link))
    except OSError:
        return False
    finally:
        target.unlink(missing_ok=True)
        link.unlink(missing_ok=True)
    return True


def test_read_file_rejects_a_symlink_escaping_the_workspace(service: RepositoryService, tmp_path: Path) -> None:
    if not _can_create_symlinks(tmp_path):
        pytest.skip("Symlink creation is not permitted in this environment.")

    output_directory = _make_run_dir(tmp_path)
    secret = tmp_path / "outside_workspace.txt"
    secret.write_text("top secret", encoding="utf-8")

    link = output_directory / "escape.txt"
    os.symlink(str(secret), str(link))

    with pytest.raises(InvalidRepositoryPathError):
        service.read_file(str(output_directory), "escape.txt")


def test_get_tree_excludes_a_symlink_escaping_the_workspace(service: RepositoryService, tmp_path: Path) -> None:
    if not _can_create_symlinks(tmp_path):
        pytest.skip("Symlink creation is not permitted in this environment.")

    output_directory = _make_run_dir(tmp_path)
    secret_dir = tmp_path / "outside_dir"
    secret_dir.mkdir()
    (secret_dir / "leaked.txt").write_text("leaked", encoding="utf-8")

    link = output_directory / "linked_dir"
    os.symlink(str(secret_dir), str(link), target_is_directory=True)
    (output_directory / "real.txt").write_text("real", encoding="utf-8")

    tree = service.get_tree(str(output_directory))

    names = {node.name for node in tree}
    assert names == {"real.txt"}


def test_search_filename_mode_matches_folders_too(service: RepositoryService, tmp_path: Path) -> None:
    output_directory = _make_run_dir(tmp_path)
    (output_directory / "src").mkdir()
    (output_directory / "src" / "widgets").mkdir()
    (output_directory / "src" / "app.py").write_text("x\n", encoding="utf-8")

    matches = service.search(str(output_directory), query="widgets", mode="filename", language=None)

    assert [m.path for m in matches] == ["src/widgets"]


def test_search_fuzzy_mode_matches_scattered_characters(service: RepositoryService, tmp_path: Path) -> None:
    output_directory = _make_run_dir(tmp_path)
    (output_directory / "user_controller.py").write_text("x\n", encoding="utf-8")
    (output_directory / "readme.md").write_text("x\n", encoding="utf-8")

    matches = service.search(str(output_directory), query="usrctrl", mode="fuzzy", language=None)

    assert [m.path for m in matches] == ["user_controller.py"]


def test_search_fuzzy_mode_returns_no_match_when_subsequence_is_absent(
    service: RepositoryService, tmp_path: Path
) -> None:
    output_directory = _make_run_dir(tmp_path)
    (output_directory / "app.py").write_text("x\n", encoding="utf-8")

    matches = service.search(str(output_directory), query="zzz", mode="fuzzy", language=None)

    assert matches == []
