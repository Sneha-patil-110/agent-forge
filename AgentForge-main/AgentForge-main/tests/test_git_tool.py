from __future__ import annotations

from pathlib import Path

import pytest
from git import Repo

from backend.tools.git_tool import GitTool


@pytest.fixture
def repo_path(tmp_path: Path) -> Path:
    repo = Repo.init(tmp_path)

    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "test@example.com")

    (tmp_path / "README.md").write_text("# Test repo\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return tmp_path


@pytest.fixture
def tool(tmp_path: Path) -> GitTool:
    return GitTool(workspace=tmp_path)


def test_status_on_clean_repo(tool: GitTool, repo_path: Path) -> None:
    result = tool.run(operation="status", repo_path=".")

    assert result.success is True
    assert result.output["is_dirty"] is False


def test_status_reports_untracked_files(tool: GitTool, repo_path: Path) -> None:
    (repo_path / "new_file.txt").write_text("content", encoding="utf-8")

    result = tool.run(operation="status", repo_path=".")

    assert result.success is True
    assert "new_file.txt" in result.output["untracked"]


def test_add_stages_a_file(tool: GitTool, repo_path: Path) -> None:
    (repo_path / "staged.txt").write_text("content", encoding="utf-8")

    result = tool.run(operation="add", repo_path=".", files="staged.txt")

    assert result.success is True

    status = tool.run(operation="status", repo_path=".")
    assert "staged.txt" in status.output["staged"]


def test_commit_creates_a_commit(tool: GitTool, repo_path: Path) -> None:
    (repo_path / "file.txt").write_text("content", encoding="utf-8")
    tool.run(operation="add", repo_path=".", files="file.txt")

    result = tool.run(operation="commit", repo_path=".", message="Add file")

    assert result.success is True
    assert isinstance(result.output, str)
    assert len(result.output) == 40


def test_commit_without_staged_changes_fails(tool: GitTool, repo_path: Path) -> None:
    result = tool.run(operation="commit", repo_path=".", message="Nothing to commit")

    assert result.success is False


def test_branch_lists_local_branches(tool: GitTool, repo_path: Path) -> None:
    result = tool.run(operation="branch", repo_path=".")

    assert result.success is True
    assert isinstance(result.output, list)
    assert len(result.output) >= 1


def test_checkout_existing_branch(tool: GitTool, repo_path: Path) -> None:
    repo = Repo(repo_path)
    repo.create_head("feature-branch")

    result = tool.run(operation="checkout", repo_path=".", branch="feature-branch")

    assert result.success is True
    assert repo.active_branch.name == "feature-branch"


def test_checkout_missing_branch_fails(tool: GitTool, repo_path: Path) -> None:
    result = tool.run(
        operation="checkout", repo_path=".", branch="does-not-exist"
    )

    assert result.success is False


def test_log_returns_commit_history(tool: GitTool, repo_path: Path) -> None:
    result = tool.run(operation="log", repo_path=".", max_count=5)

    assert result.success is True
    assert len(result.output) == 1
    assert result.output[0]["message"].strip() == "Initial commit"


def test_invalid_repository_path_is_rejected(tmp_path: Path) -> None:
    non_repo = tmp_path / "not-a-repo"
    non_repo.mkdir()

    tool = GitTool(workspace=tmp_path)
    result = tool.run(operation="status", repo_path="not-a-repo")

    assert result.success is False


def test_missing_repository_path_is_rejected(tmp_path: Path) -> None:
    tool = GitTool(workspace=tmp_path)
    result = tool.run(operation="status", repo_path="does-not-exist")

    assert result.success is False


def test_repo_path_outside_workspace_is_blocked(tool: GitTool, repo_path: Path) -> None:
    result = tool.run(operation="status", repo_path=str(repo_path.parent))

    assert result.success is False
