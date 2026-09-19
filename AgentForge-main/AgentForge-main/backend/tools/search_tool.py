from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.services.tracing_service import TracingService
from backend.tools.base_tool import BaseTool, ToolResult


class SearchTool(BaseTool):
    IGNORED_DIRECTORIES = {
        ".git",
        ".idea",
        ".vscode",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "venv",
        ".venv",
        "dist",
        "build",
    }

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
        return "search"

    @property
    def description(self) -> str:
        return (
            "Searches for files and text inside "
            "the configured project workspace."
        )

    def validate_arguments(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        operation = kwargs.get("operation")

        supported_operations = {
            "files",
            "text",
        }

        if not isinstance(operation, str):
            raise ValueError(
                "The 'operation' argument must be a string."
            )

        if operation not in supported_operations:
            raise ValueError(
                f"Unsupported search operation: "
                f"'{operation}'."
            )

        root = kwargs.get(
            "root",
            ".",
        )

        if not isinstance(
            root,
            (str, Path),
        ):
            raise ValueError(
                "The 'root' argument must be "
                "a string or Path object."
            )

        if operation == "files":
            pattern = kwargs.get(
                "pattern",
                "*",
            )

            if (
                not isinstance(pattern, str)
                or not pattern.strip()
            ):
                raise ValueError(
                    "The 'pattern' argument must "
                    "be a non empty string."
                )

        if operation == "text":
            query = kwargs.get("query")

            if (
                not isinstance(query, str)
                or not query.strip()
            ):
                raise ValueError(
                    "The 'query' argument must "
                    "be a non empty string."
                )

        max_results = kwargs.get(
            "max_results",
            100,
        )

        if (
            not isinstance(max_results, int)
            or isinstance(max_results, bool)
            or max_results < 1
            or max_results > 1000
        ):
            raise ValueError(
                "'max_results' must be an integer "
                "between 1 and 1000."
            )

        return kwargs

    def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:
        operation = kwargs["operation"]

        root = self._resolve_root(
            kwargs.get(
                "root",
                ".",
            )
        )

        operations = {
            "files": self._find_files,
            "text": self._search_text,
        }

        extra_arguments = {
            key: value
            for key, value in kwargs.items()
            if key not in {"operation", "root"}
        }

        output = operations[operation](
            root=root,
            **extra_arguments,
        )

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "tool": self.name,
                "operation": operation,
                "root": str(
                    root.relative_to(
                        self.workspace
                    )
                )
                or ".",
                "result_count": len(output),
            },
        )

    def _resolve_root(
        self,
        root: str | Path,
    ) -> Path:
        requested_root = Path(root)

        if requested_root.is_absolute():
            resolved_root = requested_root.resolve()
        else:
            resolved_root = (
                self.workspace / requested_root
            ).resolve()

        try:
            resolved_root.relative_to(
                self.workspace
            )

        except ValueError as error:
            raise PermissionError(
                "Search access outside the configured "
                "workspace is not allowed."
            ) from error

        if not resolved_root.exists():
            raise FileNotFoundError(
                f"Search root does not exist: "
                f"{resolved_root}"
            )

        if not resolved_root.is_dir():
            raise NotADirectoryError(
                f"Search root is not a directory: "
                f"{resolved_root}"
            )

        return resolved_root

    def _find_files(
        self,
        root: Path,
        **kwargs: Any,
    ) -> list[str]:
        pattern = kwargs.get(
            "pattern",
            "*",
        )

        max_results = kwargs.get(
            "max_results",
            100,
        )

        matches: list[str] = []

        for path in root.rglob(pattern):

            if not path.is_file():
                continue

            if self._is_ignored(
                path,
                root,
            ):
                continue

            matches.append(
                path.relative_to(
                    root
                ).as_posix()
            )

            if len(matches) >= max_results:
                break

        return sorted(matches)

    def _search_text(
        self,
        root: Path,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        query = kwargs["query"]

        case_sensitive = kwargs.get(
            "case_sensitive",
            False,
        )

        max_results = kwargs.get(
            "max_results",
            100,
        )

        search_query = (
            query
            if case_sensitive
            else query.casefold()
        )

        matches: list[dict[str, Any]] = []

        for file in root.rglob("*"):

            if not file.is_file():
                continue

            if self._is_ignored(
                file,
                root,
            ):
                continue

            try:
                lines = file.read_text(
                    encoding="utf-8",
                ).splitlines()

            except (
                UnicodeDecodeError,
                OSError,
            ):
                continue

            for line_number, line in enumerate(
                lines,
                start=1,
            ):

                searchable_line = (
                    line
                    if case_sensitive
                    else line.casefold()
                )

                if search_query not in searchable_line:
                    continue

                matches.append(
                    {
                        "file": file.relative_to(
                            root
                        ).as_posix(),
                        "line": line_number,
                        "content": line.strip(),
                    }
                )

                if len(matches) >= max_results:
                    return matches

        return matches

    def _is_ignored(
        self,
        path: Path,
        root: Path,
    ) -> bool:
        relative_parts = path.relative_to(
            root
        ).parts

        return any(
            part in self.IGNORED_DIRECTORIES
            for part in relative_parts
        )