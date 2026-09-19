from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from backend.state.execution_state import FailureCategory


class TestStatus(str, Enum):
    __test__ = False

    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"


class DiscoveryStatus(str, Enum):

    __test__ = False

    NOT_RECOGNIZED = "not_recognized"
    RECOGNIZED_NO_TESTS = "recognized_no_tests"
    RECOGNIZED_TESTABLE = "recognized_testable"


class TestFailure(BaseModel):
    __test__ = False

    name: str = Field(..., description="Identifier of the failing test.")

    message: str | None = Field(
        default=None,
        description="Failure message or assertion detail.",
    )

    error_type: str | None = Field(
        default=None,
        description="Exception/assertion type, e.g. 'AssertionError', 'ModuleNotFoundError', when parseable.",
    )

    file_path: str | None = Field(
        default=None,
        description="Relative path of the file containing the test, when known.",
    )

    traceback: str | None = Field(
        default=None,
        description="Extracted failure traceback or stack trace snippet.",
    )

    stdout_snippet: str | None = Field(
        default=None,
        description="Captured stdout snippet for this test failure.",
    )

    stderr_snippet: str | None = Field(
        default=None,
        description="Captured stderr snippet for this test failure.",
    )



class TesterPlan(BaseModel):
    __test__ = False

    command: list[str] = Field(
        ...,
        description="Exact test command tokens selected for execution, e.g. ['pytest'].",
    )
    testing_summary: str | None = Field(
        default=None,
        description="Concise summary of the test plan.",
    )


class TestingState(BaseModel):


    __test__ = False

    status: TestStatus = Field(
        default=TestStatus.NOT_RUN,
        description="Outcome of the most recent test execution.",
    )

    command: list[str] | None = Field(
        default=None,
        description="Exact command tokens selected for execution.",
    )

    exit_code: int | None = Field(
        default=None,
        description="Process exit code from the most recent execution.",
    )

    stdout: str = Field(
        default="",
        description="Captured standard output, possibly truncated.",
    )

    stderr: str = Field(
        default="",
        description="Captured standard error, possibly truncated.",
    )

    passed: bool = Field(
        default=False,
        description="Whether the test run passed.",
    )

    total_tests: int = Field(
        default=0,
        ge=0,
        description="Total tests reported by the test runner, when parseable.",
    )

    passed_tests: int = Field(
        default=0,
        ge=0,
        description="Tests reported as passed.",
    )

    skipped_tests: int = Field(
        default=0,
        ge=0,
        description="Tests reported as skipped.",
    )

    failed_tests: list[TestFailure] = Field(
        default_factory=list,
        description="Individual failing tests, when parseable from output.",
    )

    duration_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Wall clock duration of the execution.",
    )

    timed_out: bool = Field(
        default=False,
        description="Whether execution was terminated for exceeding the timeout.",
    )

    attempt_number: int = Field(
        default=0,
        ge=0,
        description="1-based attempt number for this testing cycle.",
    )

    error_type: str | None = Field(
        default=None,
        description=(
            "Set when a test could not meaningfully run, e.g. "
            "'command_rejected', 'no_output_directory', 'process_error'."
        ),
    )

    classification: FailureCategory | None = Field(
        default=None,
        description=(
            "Deterministic failure classification for this attempt, set by "
            "TestDiscoveryService/EnvironmentPreflightService/DependencyPreparationService "
            "/TestingService/TesterAgent. None when the run passed. Drives "
            "graph.router's infra-vs-code-repair routing decision -- see "
            "execution_state.INFRASTRUCTURE_FAILURE_CATEGORIES."
        ),
    )

    framework: str | None = Field(
        default=None,
        description="Test framework actually used, e.g. 'pytest', 'jest', 'vitest'.",
    )

    working_directory: str | None = Field(
        default=None,
        description="Relative working directory the test command was executed from.",
    )

    testing_summary: str | None = Field(
        default=None,
        description="Concise summary of the test plan or outcome.",
    )

    discovery_status: DiscoveryStatus | None = Field(
        default=None,
        description=(
            "What kind of repository/test situation this attempt represents. "
            "None only for states never touched by WorkflowNodes.tester() "
            "(e.g. the initial NOT_RUN default)."
        ),
    )

    tests_discovered: bool = Field(
        default=False,
        description="Whether TestDiscoveryService found any real test files.",
    )

    tests_executed: bool = Field(
        default=False,
        description=(
            "Whether a real test-suite process (not a compile/build check) "
            "actually ran. False means TesterAgent must not be invoked -- "
            "there is no test evidence for it to interpret."
        ),
    )

    verification_method: str | None = Field(
        default=None,
        description=(
            "What actually ran: a framework name (e.g. 'pytest', 'jest') "
            "when tests_executed is True, otherwise 'compile_check', "
            "'build_check', or 'none'."
        ),
    )

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    @model_validator(mode="after")
    def _validate_consistency(self) -> TestingState:
        if self.passed and self.status in (TestStatus.FAILED, TestStatus.ERROR, TestStatus.TIMEOUT):
            raise ValueError(
                "`passed` cannot be true when status is "
                f"'{self.status.value}'."
            )

        if self.passed and self.failed_tests:
            raise ValueError(
                "`passed` cannot be true when `failed_tests` is not empty."
            )

        if self.total_tests:
            accounted_for = self.passed_tests + len(self.failed_tests) + self.skipped_tests

            if accounted_for > self.total_tests:
                raise ValueError(
                    "`passed_tests` + `failed_tests` + `skipped_tests` "
                    "cannot exceed `total_tests`."
                )

        return self
