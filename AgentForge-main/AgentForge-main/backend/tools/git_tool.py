from __future__ import annotations

from pathlib import Path
from typing import Any

from git import (
    GitCommandError,
    InvalidGitRepositoryError,
    NoSuchPathError,
    Repo,
)

from backend.services.tracing_service import TracingService
from backend.tools.base_tool import BaseTool, ToolResult


class GitTool(BaseTool):
    def __init__(
        self,
        workspace: str | Path = ".",
        *,
        tracing_service: TracingService | None = None,
    ) -> None:
        super().__init__(tracing_service=tracing_service)

        self.workspace = Path(
            workspace
        ).resolve()

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Performs status, add, commit, branch, "
            "checkout, and log operations on Git repositories."
        )

    def validate_arguments(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        operation = kwargs.get("operation")

        supported_operations = {
            "status",
            "add",
            "commit",
            "branch",
            "checkout",
            "log",
        }

        if not isinstance(operation, str):
            raise ValueError(
                "The 'operation' argument must be a string."
            )

        if operation not in supported_operations:
            raise ValueError(
                f"Unsupported Git operation: '{operation}'."
            )

        repo_path = kwargs.get("repo_path")

        if repo_path is None:
            raise ValueError(
                "The 'repo_path' argument is required."
            )

        if not isinstance(
            repo_path,
            (str, Path),
        ):
            raise ValueError(
                "The 'repo_path' argument must be "
                "a string or Path object."
            )

        if operation == "commit":
            message = kwargs.get("message")

            if (
                not isinstance(message, str)
                or not message.strip()
            ):
                raise ValueError(
                    "A non empty commit message is required."
                )

        if operation == "checkout":
            branch = kwargs.get("branch")

            if (
                not isinstance(branch, str)
                or not branch.strip()
            ):
                raise ValueError(
                    "A valid branch name is required."
                )

        if operation == "log":
            max_count = kwargs.get(
                "max_count",
                10,
            )

            if (
                not isinstance(max_count, int)
                or isinstance(max_count, bool)
                or max_count < 1
                or max_count > 100
            ):
                raise ValueError(
                    "'max_count' must be an integer "
                    "between 1 and 100."
                )

        return kwargs

    def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:
        operation = kwargs["operation"]

        repo_path = self._resolve_path(
            kwargs["repo_path"]
        )

        repo = self._get_repo(
            repo_path
        )

        operations = {
            "status": self._status,
            "add": self._add,
            "commit": self._commit,
            "branch": self._branch,
            "checkout": self._checkout,
            "log": self._log,
        }

        try:
            output = operations[operation](
                repo,
                **kwargs,
            )

        except GitCommandError as error:
            raise RuntimeError(
                f"Git operation '{operation}' failed: "
                f"{error.stderr or error}"
            ) from error

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "tool": self.name,
                "operation": operation,
                "repository": str(
                    repo_path.relative_to(
                        self.workspace
                    )
                ),
            },
        )

    def _resolve_path(
        self,
        repo_path: str | Path,
    ) -> Path:
        requested_path = Path(
            repo_path
        )

        if requested_path.is_absolute():
            resolved_path = requested_path.resolve()
        else:
            resolved_path = (
                self.workspace / requested_path
            ).resolve()

        try:
            resolved_path.relative_to(
                self.workspace
            )

        except ValueError as error:
            raise PermissionError(
                "Git access outside the configured "
                "workspace is not allowed."
            ) from error

        return resolved_path

    def _get_repo(
        self,
        repo_path: Path,
    ) -> Repo:
        try:
            return Repo(
                repo_path,
                search_parent_directories=False,
            )

        except NoSuchPathError as error:
            raise FileNotFoundError(
                f"Repository path does not exist: "
                f"{repo_path}"
            ) from error

        except InvalidGitRepositoryError as error:
            raise ValueError(
                f"Path is not a valid Git repository: "
                f"{repo_path}"
            ) from error

    def _status(
        self,
        repo: Repo,
        **_: Any,
    ) -> dict[str, Any]:
        return {
            "branch": (
                repo.active_branch.name
                if not repo.head.is_detached
                else None
            ),
            "modified": repo.git.diff(
                "--name-only"
            ).splitlines(),
            "staged": repo.git.diff(
                "--cached",
                "--name-only",
            ).splitlines(),
            "untracked": sorted(
                repo.untracked_files
            ),
            "is_dirty": repo.is_dirty(
                untracked_files=True
            ),
        }

    def _add(
        self,
        repo: Repo,
        **kwargs: Any,
    ) -> bool:
        files = kwargs.get(
            "files",
            ".",
        )

        if isinstance(files, str):
            repo.git.add(files)

        elif isinstance(files, list):
            if not all(
                isinstance(file, str)
                for file in files
            ):
                raise ValueError(
                    "Every file path must be a string."
                )

            repo.index.add(files)

        else:
            raise ValueError(
                "'files' must be a string "
                "or a list of strings."
            )

        return True

    def _commit(
        self,
        repo: Repo,
        **kwargs: Any,
    ) -> str:
        message = kwargs["message"].strip()

        if not repo.index.diff(
            "HEAD"
        ) and repo.head.is_valid():
            raise ValueError(
                "No staged changes are available "
                "to commit."
            )

        commit = repo.index.commit(
            message
        )

        return commit.hexsha

    def _branch(
        self,
        repo: Repo,
        **_: Any,
    ) -> list[str]:
        return sorted(
            branch.name
            for branch in repo.branches
        )

    def _checkout(
        self,
        repo: Repo,
        **kwargs: Any,
    ) -> bool:
        branch_name = kwargs[
            "branch"
        ].strip()

        branch_names = {
            branch.name
            for branch in repo.branches
        }

        if branch_name not in branch_names:
            raise ValueError(
                f"Branch '{branch_name}' does not exist."
            )

        repo.git.checkout(
            branch_name
        )

        return True

    def _log(
        self,
        repo: Repo,
        **kwargs: Any,
    ) -> list[dict[str, str]]:
        max_count = kwargs.get(
            "max_count",
            10,
        )

        return [
            {
                "hash": commit.hexsha,
                "short_hash": commit.hexsha[:7],
                "message": commit.message.strip(),
                "author": commit.author.name,
                "committed_at": (
                    commit.committed_datetime.isoformat()
                ),
            }
            for commit in repo.iter_commits(
                max_count=max_count
            )
        ]