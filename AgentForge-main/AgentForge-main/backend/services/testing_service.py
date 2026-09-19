
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from backend.core.constants import MAX_TEST_OUTPUT_CHARS, TEST_EXECUTION_TIMEOUT
from backend.services.project_venv import substitute_python_executable, venv_python_path
from backend.state.project_state import ProjectState
from backend.state.test_plan import TestPlan, TestStage
from backend.state.testing_state import TestFailure, TestingState, TestStatus
from backend.tools.base_tool import ToolResult
from backend.tools.tool_registry import ToolRegistry


logger = logging.getLogger(__name__)

_PYTHON_EXECUTABLE_NAMES = {"python", "python3"}
_ALLOWED_PYTHON_MODULES = {"pytest", "unittest", "compileall"}
_ALLOWED_DIRECT_EXECUTABLES = {"pytest"}
_ALLOWED_NPM_SUBCOMMANDS = {"test", "run"}
_ALLOWED_NPM_RUN_SCRIPTS = {"build", "test"}
_ALLOWED_NPX_PACKAGES = {"jest", "vitest"}

_SUMMARY_COUNT_PATTERN = re.compile(r"(\d+)\s+(passed|failed|error|skipped)")
_FAILED_TEST_PATTERN = re.compile(
    r"^FAILED\s+(?P<name>\S+)(?:\s+-\s+(?P<message>.*))?$",
    re.MULTILINE,
)
_JS_COUNT_PATTERN = re.compile(r"(\d+)\s+(passed|failed|skipped|total)\b")
_JS_FAILED_TEST_PATTERN = re.compile(r"^\s*(?:✕|×)\s+(?P<name>.+?)(?:\s+\(\d+\s*m?s\))?\s*$", re.MULTILINE)

_JS_FRAMEWORKS = {"jest", "vitest"}


class TestingService:
    __test__ = False

    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def execute(
        self,
        *,
        project: ProjectState,
        command: list[str] | None,
        attempt_number: int,
    ) -> TestingState:
        if not project.output_directory:
            return TestingState(
                status=TestStatus.ERROR,
                error_type="no_output_directory",
                attempt_number=attempt_number,
                testing_summary="No project output directory is configured; nothing to test.",
            )

        validation_error = self._validate_command(command)

        if validation_error is not None:
            logger.warning("Test command rejected: %s", validation_error)

            return TestingState(
                status=TestStatus.ERROR,
                command=command,
                error_type="command_rejected",
                attempt_number=attempt_number,
                testing_summary=validation_error,
            )

        logger.info(
            "Testing started (attempt %d): %s", attempt_number, " ".join(command)
        )

        terminal_tool = self.tool_registry.get("terminal")

        started_at = time.monotonic()

        result = terminal_tool.run(
            command=command,
            cwd=str(Path(project.output_directory)),
            timeout=TEST_EXECUTION_TIMEOUT,
        )

        duration_seconds = time.monotonic() - started_at

        return self._build_testing_state(
            command=command,
            result=result,
            attempt_number=attempt_number,
            duration_seconds=duration_seconds,
        )

    def execute_stage(
        self,
        *,
        project: ProjectState,
        plan: TestPlan,
        stage: TestStage,
        attempt_number: int,
        targeted_tests: list[str] | None = None,
    ) -> TestingState:

        if not project.output_directory:
            return TestingState(
                status=TestStatus.ERROR,
                error_type="no_output_directory",
                attempt_number=attempt_number,
                testing_summary="No project output directory is configured; nothing to test.",
            )

        command = stage.command

        if targeted_tests and plan.targeted_test_capability:
            command = self.build_targeted_command(command, targeted_tests)

        cwd = (
            project.output_directory
            if plan.working_directory == "."
            else str(Path(project.output_directory) / plan.working_directory)
        )

        if plan.runtime == "python":
            venv_python = venv_python_path(cwd)
            if venv_python.exists():
                command = substitute_python_executable(command, venv_python)

        validation_error = self._validate_command(command)

        if validation_error is not None:
            logger.warning("Test command rejected: %s", validation_error)

            return TestingState(
                status=TestStatus.ERROR,
                command=command,
                error_type="command_rejected",
                attempt_number=attempt_number,
                framework=plan.framework,
                working_directory=plan.working_directory,
                testing_summary=validation_error,
            )

        logger.info(
            "Testing started (attempt %d, stage=%s): %s", attempt_number, stage.name, " ".join(command)
        )

        terminal_tool = self.tool_registry.get("terminal")

        started_at = time.monotonic()

        result = terminal_tool.run(
            command=command,
            cwd=cwd,
            timeout=TEST_EXECUTION_TIMEOUT,
        )

        duration_seconds = time.monotonic() - started_at

        state = self._build_testing_state(
            command=command,
            result=result,
            attempt_number=attempt_number,
            duration_seconds=duration_seconds,
            framework=plan.framework,
        )
        state.working_directory = plan.working_directory

        return state

    @staticmethod
    def _validate_command(command: list[str] | None) -> str | None:
        if not isinstance(command, list) or not command:
            return "Test command must be a non-empty list of arguments."

        if not all(isinstance(token, str) and token.strip() for token in command):
            return "Every test command token must be a non-empty string."

        executable = Path(command[0]).stem.lower()

        if executable in _PYTHON_EXECUTABLE_NAMES:
            if (
                len(command) < 3
                or command[1] != "-m"
                or command[2] not in _ALLOWED_PYTHON_MODULES
            ):
                allowed = ", ".join(sorted(_ALLOWED_PYTHON_MODULES))
                return f"Only 'python -m <{allowed}>' invocations are permitted."

            return None

        if executable in _ALLOWED_DIRECT_EXECUTABLES:
            return None

        if executable == "npm":
            if len(command) < 2 or command[1] not in _ALLOWED_NPM_SUBCOMMANDS:
                return "Only 'npm test' or 'npm run <build|test>' invocations are permitted."
            if command[1] == "run" and (len(command) < 3 or command[2] not in _ALLOWED_NPM_RUN_SCRIPTS):
                allowed = ", ".join(sorted(_ALLOWED_NPM_RUN_SCRIPTS))
                return f"Only 'npm run <{allowed}>' invocations are permitted."
            return None

        if executable == "npx":
            if len(command) < 2 or command[1] not in _ALLOWED_NPX_PACKAGES:
                allowed = ", ".join(sorted(_ALLOWED_NPX_PACKAGES))
                return f"Only 'npx <{allowed}>' invocations are permitted."
            return None

        return f"Command '{executable}' is not an allowed test runner."

    def _build_testing_state(
        self,
        *,
        command: list[str],
        result: ToolResult,
        attempt_number: int,
        duration_seconds: float,
        framework: str | None = None,
    ) -> TestingState:
        metadata = result.metadata or {}

        if not result.success and result.output is None:
            timed_out = "timeout" in (result.error or "").lower()

            return TestingState(
                status=TestStatus.TIMEOUT if timed_out else TestStatus.ERROR,
                command=command,
                stdout=self._truncate(metadata.get("stdout", "")),
                stderr=self._truncate(metadata.get("stderr", "")),
                timed_out=timed_out,
                duration_seconds=duration_seconds,
                error_type="timeout" if timed_out else "process_error",
                attempt_number=attempt_number,
                framework=framework,
                testing_summary=result.error,
            )

        output = result.output or {}
        stdout = self._truncate(output.get("stdout", ""))
        stderr = self._truncate(output.get("stderr", ""))
        exit_code = output.get("return_code")
        passed = exit_code == 0

        is_js = framework in _JS_FRAMEWORKS
        counts = self._parse_js_summary_counts(stdout) if is_js else self._parse_summary_counts(stdout)
        failed_tests = (
            (self._parse_js_failed_tests(stdout, stderr) if is_js else self._parse_failed_tests(stdout, stderr))
            if not passed
            else []
        )

        return TestingState(
            status=TestStatus.PASSED if passed else TestStatus.FAILED,
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            passed=passed,
            total_tests=counts["total"],
            passed_tests=counts["passed"],
            skipped_tests=counts["skipped"],
            failed_tests=failed_tests,
            duration_seconds=duration_seconds,
            attempt_number=attempt_number,
            framework=framework,
            testing_summary=(
                "All tests passed." if passed else f"{len(failed_tests)} test(s) failed."
            ),
        )

    @staticmethod
    def build_targeted_command(command: list[str], targeted_tests: list[str]) -> list[str]:
        if not targeted_tests or not command:
            return command

        executable = Path(command[0]).stem.lower()

        if executable in _ALLOWED_DIRECT_EXECUTABLES:
            return [command[0], *targeted_tests]

        if len(command) >= 3 and command[0] in _PYTHON_EXECUTABLE_NAMES and command[2] == "pytest":
            return [command[0], command[1], command[2], *targeted_tests]

        if executable == "npx" and len(command) >= 2 and command[1] in _ALLOWED_NPX_PACKAGES:
            return [*command, *targeted_tests]

        return command

    @staticmethod
    def _truncate(text: str) -> str:

        if len(text) <= MAX_TEST_OUTPUT_CHARS:
            return text

        half = MAX_TEST_OUTPUT_CHARS // 2
        omitted = len(text) - MAX_TEST_OUTPUT_CHARS

        return f"{text[:half]}\n... [{omitted} characters truncated] ...\n{text[-half:]}"

    @staticmethod
    def _parse_summary_counts(stdout: str) -> dict[str, int]:
        counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}

        for count, label in _SUMMARY_COUNT_PATTERN.findall(stdout):
            counts[label] += int(count)

        total = counts["passed"] + counts["failed"] + counts["error"] + counts["skipped"]

        return {
            "total": total,
            "passed": counts["passed"],
            "skipped": counts["skipped"],
        }

    @staticmethod
    def _parse_failed_tests(stdout: str, stderr: str = "") -> list[TestFailure]:
        failures: list[TestFailure] = []
        full_text = f"{stdout}\n{stderr}"

        failure_blocks: dict[str, str] = {}
        if "FAILURES" in full_text:
            sections = full_text.split("FAILURES")
            if len(sections) > 1:
                fail_sec = sections[1].split("short test summary info")[0]
                raw_blocks = re.split(r"_{3,}\s*(.*?)\s*_{3,}", fail_sec)
                for i in range(1, len(raw_blocks) - 1, 2):
                    test_header = raw_blocks[i].strip()
                    block_body = raw_blocks[i + 1].strip()
                    failure_blocks[test_header] = block_body[:1000]

        for match in _FAILED_TEST_PATTERN.finditer(stdout):
            name = match.group("name")
            message = match.group("message")
            file_path = name.split("::", 1)[0] if "::" in name else None

            tb = None
            clean_name = name.rsplit("[", 1)[0] if "[" in name else name
            for header, body in failure_blocks.items():
                if header in name or name in header or header in clean_name:
                    tb = body
                    break

            failures.append(
                TestFailure(
                    name=name,
                    message=message,
                    file_path=file_path,
                    traceback=tb,
                    stdout_snippet=stdout[:1000] if stdout else None,
                    stderr_snippet=stderr[:1000] if stderr else None,
                )
            )

        return failures

    @staticmethod
    def _parse_js_summary_counts(stdout: str) -> dict[str, int]:

        counts = {"passed": 0, "failed": 0, "skipped": 0, "total": 0}

        for count, label in _JS_COUNT_PATTERN.findall(stdout):
            counts[label] += int(count)

        if not counts["total"]:
            counts["total"] = counts["passed"] + counts["failed"] + counts["skipped"]

        return {"total": counts["total"], "passed": counts["passed"], "skipped": counts["skipped"]}

    @staticmethod
    def _parse_js_failed_tests(stdout: str, stderr: str = "") -> list[TestFailure]:
        failures: list[TestFailure] = []

        for match in _JS_FAILED_TEST_PATTERN.finditer(stdout):
            name = match.group("name").strip()

            failures.append(
                TestFailure(
                    name=name,
                    stdout_snippet=stdout[:1000] if stdout else None,
                    stderr_snippet=stderr[:1000] if stderr else None,
                )
            )

        return failures

