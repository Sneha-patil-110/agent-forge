from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.tools.terminal_tool import TerminalTool


@pytest.fixture
def tool(tmp_path: Path) -> TerminalTool:
    return TerminalTool(workspace=tmp_path)


def _python_command(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_allowed_command_captures_stdout_and_exit_code(tool: TerminalTool) -> None:
    result = tool.run(command=_python_command("print('hello')"))

    assert result.success is True
    assert result.output["return_code"] == 0
    assert "hello" in result.output["stdout"]


def test_nonzero_exit_code_is_captured_as_failure(tool: TerminalTool) -> None:
    result = tool.run(command=_python_command("import sys; sys.exit(3)"))

    assert result.success is False
    assert result.output["return_code"] == 3


def test_stderr_is_captured(tool: TerminalTool) -> None:
    result = tool.run(
        command=_python_command(
            "import sys; sys.stderr.write('boom'); sys.exit(1)"
        )
    )

    assert result.success is False
    assert "boom" in result.output["stderr"]


def test_blocked_command_is_rejected(tool: TerminalTool) -> None:
    result = tool.run(command="shutdown")

    assert result.success is False
    assert "not permitted" in (result.error or "")


def test_timeout_is_enforced(tool: TerminalTool) -> None:
    result = tool.run(
        command=_python_command("import time; time.sleep(5)"),
        timeout=1,
    )

    assert result.success is False
    assert "timeout" in (result.error or "").lower()


def test_invalid_working_directory_outside_workspace_is_blocked(
    tool: TerminalTool, tmp_path: Path
) -> None:
    outside = tmp_path.parent

    result = tool.run(
        command=_python_command("print('hi')"),
        cwd=str(outside),
    )

    assert result.success is False


def test_missing_working_directory_is_rejected(tool: TerminalTool) -> None:
    result = tool.run(
        command=_python_command("print('hi')"),
        cwd="does-not-exist",
    )

    assert result.success is False


def test_empty_command_is_rejected(tool: TerminalTool) -> None:
    result = tool.run(command="")

    assert result.success is False


def test_command_runs_inside_configured_workspace(
    tool: TerminalTool, tmp_path: Path
) -> None:
    result = tool.run(
        command=_python_command(
            "import pathlib; print(pathlib.Path.cwd())"
        )
    )

    assert result.success is True
    assert str(tmp_path) in result.output["stdout"]


def test_list_command_argument_is_not_shell_interpreted(
    tool: TerminalTool, tmp_path: Path
) -> None:

    marker = tmp_path / "should_not_exist.txt"

    result = tool.run(
        command=_python_command("print('safe')")
        + [f"; echo pwned > {marker}"]
    )

    assert result.success is True
    assert not marker.exists()
