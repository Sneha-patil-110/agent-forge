from __future__ import annotations

from pathlib import Path

from backend.services.testing_service import TestingService
from backend.state.project_state import ProjectState
from backend.state.testing_state import TestStatus
from backend.tools.terminal_tool import TerminalTool
from backend.tools.tool_registry import ToolRegistry


def _make_service(workspace: Path) -> TestingService:
    registry = ToolRegistry()
    registry.register(TerminalTool(workspace=workspace))
    return TestingService(registry)


def test_allows_pytest_direct():
    assert TestingService._validate_command(["pytest"]) is None


def test_allows_python_module_pytest():
    assert TestingService._validate_command(["python", "-m", "pytest"]) is None


def test_allows_python_module_unittest():
    assert TestingService._validate_command(["python", "-m", "unittest"]) is None


def test_allows_python_module_compileall():
    assert (
        TestingService._validate_command(["python", "-m", "compileall", "."]) is None
    )


def test_rejects_non_list_command():
    assert TestingService._validate_command("pytest") is not None
    assert TestingService._validate_command(None) is not None


def test_rejects_empty_command():
    assert TestingService._validate_command([]) is not None


def test_rejects_python_dash_c():
    assert TestingService._validate_command(["python", "-c", "print(1)"]) is not None


def test_rejects_python_module_not_allowlisted():
    assert TestingService._validate_command(["python", "-m", "pip", "install", "x"]) is not None
    assert TestingService._validate_command(["python", "-m", "http.server"]) is not None


def test_rejects_shell_chaining_attempts():
    assert TestingService._validate_command(["sh", "-c", "rm -rf /"]) is not None
    assert TestingService._validate_command(["bash", "-c", "echo hi"]) is not None
    assert TestingService._validate_command(["cmd.exe", "/c", "dir"]) is not None
    assert TestingService._validate_command(["powershell", "-Command", "ls"]) is not None


def test_rejects_destructive_and_mutation_commands():
    assert TestingService._validate_command(["rm", "-rf", "."]) is not None
    assert TestingService._validate_command(["git", "push"]) is not None
    assert TestingService._validate_command(["pip", "install", "x"]) is not None
    assert TestingService._validate_command(["npm", "publish"]) is not None
    assert TestingService._validate_command(["curl", "http://evil.example"]) is not None


def test_rejects_pipe_and_redirect_looking_tokens_as_part_of_unallowed_executable():
    assert TestingService._validate_command(["echo", "hi", ">", "file.txt"]) is not None


def test_truncate_leaves_short_text_untouched():
    text = "short output"
    assert TestingService._truncate(text) == text


def test_truncate_long_text():
    from backend.core.constants import MAX_TEST_OUTPUT_CHARS

    text = "x" * (MAX_TEST_OUTPUT_CHARS + 500)
    truncated = TestingService._truncate(text)

    assert len(truncated) < len(text)
    assert truncated.startswith("x" * 10)
    assert "truncated" in truncated


def test_no_output_directory_returns_error_without_executing(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    project = ProjectState(output_directory=None)

    result = service.execute(project=project, command=["pytest"], attempt_number=1)

    assert result.status == TestStatus.ERROR
    assert result.error_type == "no_output_directory"


def test_rejected_command_returns_error_without_executing(tmp_path: Path) -> None:
    service = _make_service(tmp_path)
    project = ProjectState(output_directory=str(tmp_path))

    result = service.execute(
        project=project, command=["rm", "-rf", "."], attempt_number=1
    )

    assert result.status == TestStatus.ERROR
    assert result.error_type == "command_rejected"
    assert result.exit_code is None


def test_real_passing_pytest_run(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    service = _make_service(tmp_path)
    project = ProjectState(output_directory=str(tmp_path))

    result = service.execute(
        project=project,
        command=["python", "-m", "pytest"],
        attempt_number=1,
    )

    assert result.status == TestStatus.PASSED
    assert result.passed is True
    assert result.exit_code == 0
    assert result.failed_tests == []
    assert result.duration_seconds is not None
    assert result.duration_seconds >= 0
    assert result.attempt_number == 1
    assert "test_add" in result.stdout or result.passed_tests >= 1


def test_real_failing_pytest_run_captures_failure_evidence(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def divide(a, b):\n    return a / b\n", encoding="utf-8"
    )
    (tmp_path / "test_calc.py").write_text(
        "import pytest\n"
        "from calc import divide\n\n\n"
        "def test_divide_by_zero():\n"
        "    with pytest.raises(ValueError):\n"
        "        divide(1, 0)\n",
        encoding="utf-8",
    )

    service = _make_service(tmp_path)
    project = ProjectState(output_directory=str(tmp_path))

    result = service.execute(
        project=project,
        command=["python", "-m", "pytest"],
        attempt_number=1,
    )

    assert result.status == TestStatus.FAILED
    assert result.passed is False
    assert result.exit_code != 0
    assert "ZeroDivisionError" in result.stdout or "ZeroDivisionError" in result.stderr
    assert len(result.failed_tests) >= 1
    assert any(
        "test_divide_by_zero" in failure.name for failure in result.failed_tests
    )


def test_real_syntax_error_is_detected_and_captured(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def add(a, b)\n    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )

    service = _make_service(tmp_path)
    project = ProjectState(output_directory=str(tmp_path))

    result = service.execute(
        project=project,
        command=["python", "-m", "pytest"],
        attempt_number=1,
    )

    assert result.status == TestStatus.FAILED
    assert result.passed is False
    assert result.exit_code != 0
    assert "SyntaxError" in result.stdout or "SyntaxError" in result.stderr


def test_real_timeout_is_enforced_and_recorded(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "test_slow.py").write_text(
        "import time\n\n\ndef test_slow():\n    time.sleep(10)\n",
        encoding="utf-8",
    )

    import backend.services.testing_service as testing_service_module

    monkeypatch.setattr(testing_service_module, "TEST_EXECUTION_TIMEOUT", 2)

    service = _make_service(tmp_path)
    project = ProjectState(output_directory=str(tmp_path))

    result = service.execute(
        project=project,
        command=["python", "-m", "pytest"],
        attempt_number=1,
    )

    assert result.status == TestStatus.TIMEOUT
    assert result.timed_out is True
    assert result.passed is False
    assert result.duration_seconds is not None
    assert result.duration_seconds < 9
