from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from backend.core.workspace import SOURCE_ROOT
from backend.services.tracing_service import TracingService
from backend.tools.base_tool import BaseTool, ToolResult

_MUTATING_OPERATIONS = {"write", "append", "delete", "mkdir", "move", "copy", "rmdir"}


class FilesystemTool(BaseTool):

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
        return "filesystem"

    @property
    def description(self) -> str:
        return (
            "Reads, writes, appends, deletes, creates, "
            "checks, and lists files inside the workspace."
        )

    def validate_arguments(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        operation = kwargs.get("operation")

        supported_operations = {
            "read",
            "write",
            "append",
            "delete",
            "exists",
            "mkdir",
            "list",
            "move",
            "copy",
            "rmdir",
        }

        if not isinstance(operation, str):
            raise ValueError(
                "The 'operation' argument must be a string."
            )

        if operation not in supported_operations:
            raise ValueError(
                f"Unsupported filesystem operation: "
                f"'{operation}'."
            )

        raw_path = kwargs.get("path")

        if raw_path is None:
            raise ValueError(
                "The 'path' argument is required."
            )

        if not isinstance(
            raw_path,
            (str, Path),
        ):
            raise ValueError(
                "The 'path' argument must be a string "
                "or Path object."
            )

        if operation in {
            "write",
            "append",
        }:
            content = kwargs.get("content")

            if not isinstance(content, str):
                raise ValueError(
                    "The 'content' argument must be "
                    "a string."
                )

        if operation in {"move", "copy"}:
            destination = kwargs.get("destination")

            if not isinstance(destination, (str, Path)):
                raise ValueError(
                    "The 'destination' argument is required for "
                    f"'{operation}' and must be a string or Path object."
                )

        return kwargs

    def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:
        operation = kwargs["operation"]

        path = self._resolve_path(
            kwargs["path"]
        )

        if (
            path == self.workspace
            and operation
            in {
                "write",
                "append",
                "delete",
            }
        ):
            raise PermissionError(
                "The workspace root cannot be "
                "modified as a file."
            )

        if operation in _MUTATING_OPERATIONS:
            self._guard_source_root(path)

        operations = {
            "read": self._read_file,
            "write": self._write_file,
            "append": self._append_file,
            "delete": self._delete_file,
            "exists": self._exists,
            "mkdir": self._mkdir,
            "list": self._list_directory,
            "move": self._move,
            "copy": self._copy,
            "rmdir": self._rmdir,
        }

        extra_arguments = {
            key: value
            for key, value in kwargs.items()
            if key not in {"operation", "path"}
        }

        if operation in {"move", "copy"}:
            destination = self._resolve_path(extra_arguments["destination"])
            self._guard_source_root(destination)
            extra_arguments["destination"] = destination

        output = operations[operation](
            path,
            **extra_arguments,
        )

        return ToolResult(
            success=True,
            output=output,
            metadata={
                "tool": self.name,
                "operation": operation,
                "path": str(
                    path.relative_to(
                        self.workspace
                    )
                ),
            },
        )

    def _resolve_path(
        self,
        path: str | Path,
    ) -> Path:
        requested_path = Path(path)

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
                "Filesystem access outside the "
                "configured workspace is not allowed."
            ) from error

        return resolved_path

    @staticmethod
    def _guard_source_root(path: Path) -> None:
        try:
            path.relative_to(SOURCE_ROOT)

        except ValueError:
            return

        raise PermissionError(
            "Writing to the AgentForge source tree is not allowed: "
            f"{path}"
        )

    def _read_file(
        self,
        path: Path,
        **_: Any,
    ) -> str:
        if not path.exists():
            raise FileNotFoundError(
                f"File does not exist: {path}"
            )

        if not path.is_file():
            raise IsADirectoryError(
                f"Path is not a file: {path}"
            )

        return path.read_text(
            encoding="utf-8",
        )

    def _write_file(
        self,
        path: Path,
        **kwargs: Any,
    ) -> bool:
        content = kwargs["content"]

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            content,
            encoding="utf-8",
        )

        return True

    def _append_file(
        self,
        path: Path,
        **kwargs: Any,
    ) -> bool:
        content = kwargs["content"]

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            mode="a",
            encoding="utf-8",
        ) as file:
            file.write(content)

        return True

    def _delete_file(
        self,
        path: Path,
        **_: Any,
    ) -> bool:
        if not path.exists():
            return False

        if not path.is_file():
            raise IsADirectoryError(
                f"Path is not a file: {path}"
            )

        path.unlink()

        return True

    def _exists(
        self,
        path: Path,
        **_: Any,
    ) -> bool:
        return path.exists()

    def _mkdir(
        self,
        path: Path,
        **_: Any,
    ) -> bool:
        path.mkdir(
            parents=True,
            exist_ok=True,
        )

        return True

    def _list_directory(
        self,
        path: Path,
        **_: Any,
    ) -> list[str]:
        if not path.exists():
            return []

        if not path.is_dir():
            raise NotADirectoryError(
                f"Path is not a directory: {path}"
            )

        return sorted(
            item.name
            for item in path.iterdir()
        )

    def _move(
        self,
        path: Path,
        *,
        destination: Path,
        **_: Any,
    ) -> bool:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        if destination.exists():
            raise FileExistsError(f"Destination already exists: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))

        return True

    def _copy(
        self,
        path: Path,
        *,
        destination: Path,
        **_: Any,
    ) -> bool:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        if destination.exists():
            raise FileExistsError(f"Destination already exists: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)

        if path.is_dir():
            shutil.copytree(path, destination)
        else:
            shutil.copy2(path, destination)

        return True

    def _rmdir(
        self,
        path: Path,
        **_: Any,
    ) -> bool:
        if not path.exists():
            return False

        if not path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {path}")

        shutil.rmtree(path)

        return True