from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from backend.services.tracing_service import TracingService
from backend.tools.base_tool import BaseTool, ToolResult


class TerminalTool(BaseTool):
    DEFAULT_TIMEOUT = 60
    MAX_TIMEOUT = 300

    BLOCKED_COMMANDS = {
        "format",
        "shutdown",
        "restart",
        "reboot",
        "poweroff",
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
        return "terminal"

    @property
    def description(self) -> str:
        return (
            "Executes terminal commands inside the "
            "configured project workspace."
        )

    def validate_arguments(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        command = kwargs.get("command")

        if not isinstance(
            command,
            (str, list),
        ):
            raise ValueError(
                "The 'command' argument must be "
                "a string or a list of strings."
            )

        if isinstance(command, str):

            if not command.strip():
                raise ValueError(
                    "The 'command' argument cannot be empty."
                )

        else:

            if not command:
                raise ValueError(
                    "The command list cannot be empty."
                )

            if not all(
                isinstance(item, str)
                and item.strip()
                for item in command
            ):
                raise ValueError(
                    "Every command item must be "
                    "a non empty string."
                )

        timeout = kwargs.get(
            "timeout",
            self.DEFAULT_TIMEOUT,
        )

        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or timeout < 1
            or timeout > self.MAX_TIMEOUT
        ):
            raise ValueError(
                f"'timeout' must be an integer between "
                f"1 and {self.MAX_TIMEOUT} seconds."
            )

        cwd = kwargs.get(
            "cwd",
            ".",
        )

        if not isinstance(
            cwd,
            (str, Path),
        ):
            raise ValueError(
                "The 'cwd' argument must be "
                "a string or Path object."
            )

        self._validate_command(command)

        return kwargs

    def execute(
        self,
        **kwargs: Any,
    ) -> ToolResult:
        command = kwargs["command"]

        timeout = kwargs.get(
            "timeout",
            self.DEFAULT_TIMEOUT,
        )

        cwd = self._resolve_directory(
            kwargs.get(
                "cwd",
                ".",
            )
        )

        use_shell = isinstance(
            command,
            str,
        )

        executable_command = (
            command
            if use_shell
            else list(command)
        )

        try:

            result = subprocess.run(
                executable_command,
                cwd=cwd,
                shell=use_shell,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

        except subprocess.TimeoutExpired as error:

            return ToolResult(
                success=False,
                output=None,
                error=(
                    "Command execution exceeded "
                    f"the {timeout} second timeout."
                ),
                metadata={
                    "tool": self.name,
                    "command": command,
                    "timeout": timeout,
                    "stdout": self._decode_output(
                        error.stdout
                    ),
                    "stderr": self._decode_output(
                        error.stderr
                    ),
                },
            )

        except OSError as error:

            return ToolResult(
                success=False,
                output=None,
                error=str(error),
                metadata={
                    "tool": self.name,
                    "command": command,
                },
            )

        return ToolResult(
            success=result.returncode == 0,
            output={
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode,
            },
            error=(
                None
                if result.returncode == 0
                else (
                    result.stderr.strip()
                    or (
                        "Command failed with return code "
                        f"{result.returncode}."
                    )
                )
            ),
            metadata={
                "tool": self.name,
                "command": command,
                "cwd": (
                    cwd.relative_to(
                        self.workspace
                    ).as_posix()
                    or "."
                ),
                "timeout": timeout,
            },
        )

    def _resolve_directory(
        self,
        directory: str | Path,
    ) -> Path:
        requested_directory = Path(
            directory
        )

        if requested_directory.is_absolute():

            resolved_directory = (
                requested_directory.resolve()
            )

        else:

            resolved_directory = (
                self.workspace
                / requested_directory
            ).resolve()

        try:

            resolved_directory.relative_to(
                self.workspace
            )

        except ValueError as error:

            raise PermissionError(
                "Terminal execution outside the "
                "configured workspace is not allowed."
            ) from error

        if not resolved_directory.exists():

            raise FileNotFoundError(
                "Working directory does not exist: "
                f"{resolved_directory}"
            )

        if not resolved_directory.is_dir():

            raise NotADirectoryError(
                "Working directory is not a directory: "
                f"{resolved_directory}"
            )

        return resolved_directory

    def _validate_command(
        self,
        command: str | list[str],
    ) -> None:
        command_parts = (
            shlex.split(
                command,
                posix=False,
            )
            if isinstance(command, str)
            else command
        )

        if not command_parts:
            raise ValueError(
                "The command cannot be empty."
            )

        executable = Path(
            command_parts[0]
        ).stem.lower()

        if executable in self.BLOCKED_COMMANDS:

            raise PermissionError(
                f"The command '{executable}' "
                "is not permitted."
            )

    @staticmethod
    def _decode_output(
        output: str | bytes | None,
    ) -> str:

        if output is None:
            return ""

        if isinstance(
            output,
            bytes,
        ):
            return output.decode(
                encoding="utf-8",
                errors="replace",
            )

        return output