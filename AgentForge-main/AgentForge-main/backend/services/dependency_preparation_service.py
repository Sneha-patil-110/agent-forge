
from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from backend.core.constants import (
    DEPENDENCY_INSTALL_TIMEOUT,
    MAX_DEPENDENCY_INSTALL_RETRIES,
    MAX_TEST_OUTPUT_CHARS,
)
from backend.services.pip_failure_classifier import PipFailureKind, classify_pip_failure, summarize_pip_failure
from backend.services.project_venv import ensure_pytest_installed, ensure_venv, substitute_python_executable
from backend.state.test_plan import TestPlan
from backend.tools.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


class DependencyPreparationResult(BaseModel):
    working_directory: str = Field(...)
    package_manager: str | None = Field(default=None)
    command: list[str] | None = Field(default=None)
    skipped: bool = Field(
        default=False,
        description="True when the plan had no dependency manifest -- nothing to install.",
    )
    success: bool = Field(default=True)
    stdout: str = Field(default="")
    stderr: str = Field(default="")
    duration_seconds: float | None = Field(default=None)
    error_message: str | None = Field(default=None)
    failure_kind: PipFailureKind | None = Field(
        default=None,
        description=(
            "None on success. Otherwise what kind of failure this is, after "
            "any transient retries are exhausted -- drives WorkflowNodes."
            "tester()'s repair-vs-terminal routing."
        ),
    )
    attempts: int = Field(default=0, description="How many install attempts were actually made.")


class DependencyPreparationService:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        *,
        max_retries: int = MAX_DEPENDENCY_INSTALL_RETRIES,
        retry_delay_seconds: float = 2.0,
    ) -> None:
        self.tool_registry = tool_registry
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def prepare(self, *, project_root: str, plan: TestPlan) -> DependencyPreparationResult:
        if not plan.dependency_manifest or not plan.package_manager:
            return DependencyPreparationResult(
                working_directory=plan.working_directory,
                skipped=True,
            )

        command = self._build_command(plan)

        if command is None:
            return DependencyPreparationResult(
                working_directory=plan.working_directory,
                package_manager=plan.package_manager,
                skipped=True,
            )

        cwd = str(Path(project_root) / plan.working_directory) if plan.working_directory != "." else project_root

        if plan.package_manager == "pip":
            try:
                venv_python = ensure_venv(cwd)
                ensure_pytest_installed(venv_python)
            except (RuntimeError, OSError, TimeoutError) as error:
                return DependencyPreparationResult(
                    working_directory=plan.working_directory,
                    package_manager=plan.package_manager,
                    command=command,
                    success=False,
                    failure_kind=PipFailureKind.TRANSIENT,
                    error_message=f"Could not prepare the project's virtual environment: {error}",
                )
            command = substitute_python_executable(command, venv_python)

        terminal_tool = self.tool_registry.get("terminal")

        attempts = 0
        last_result: DependencyPreparationResult | None = None

        while attempts < 1 + self.max_retries:
            attempts += 1
            last_result = self._run_once(
                terminal_tool=terminal_tool,
                command=command,
                cwd=cwd,
                plan=plan,
                attempts=attempts,
            )

            if last_result.success or last_result.failure_kind != PipFailureKind.TRANSIENT:
                return last_result

            if attempts < 1 + self.max_retries:
                logger.warning(
                    "Dependency installation hit a transient failure (attempt %d/%d): %s",
                    attempts,
                    1 + self.max_retries,
                    last_result.error_message,
                )
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds)

        assert last_result is not None
        return last_result

    def _run_once(
        self,
        *,
        terminal_tool,
        command: list[str],
        cwd: str,
        plan: TestPlan,
        attempts: int,
    ) -> DependencyPreparationResult:
        started_at = time.monotonic()

        result = terminal_tool.run(
            command=command,
            cwd=cwd,
            timeout=DEPENDENCY_INSTALL_TIMEOUT,
        )

        duration_seconds = time.monotonic() - started_at

        if not result.success and result.output is None:
            timed_out = "timeout" in (result.error or "").lower()

            return DependencyPreparationResult(
                working_directory=plan.working_directory,
                package_manager=plan.package_manager,
                command=command,
                success=False,
                duration_seconds=duration_seconds,
                failure_kind=PipFailureKind.TRANSIENT,
                error_message=(
                    f"Dependency installation timed out after {DEPENDENCY_INSTALL_TIMEOUT}s."
                    if timed_out
                    else f"Dependency installation could not start: {result.error}"
                ),
                attempts=attempts,
            )

        output = result.output or {}
        stdout = self._truncate(output.get("stdout", ""))
        stderr = self._truncate(output.get("stderr", ""))
        exit_code = output.get("return_code")
        success = exit_code == 0

        if success:
            return DependencyPreparationResult(
                working_directory=plan.working_directory,
                package_manager=plan.package_manager,
                command=command,
                success=True,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration_seconds,
                attempts=attempts,
            )

        failure_kind = (
            classify_pip_failure(stdout=stdout, stderr=stderr)
            if plan.package_manager == "pip"
            else PipFailureKind.DEPENDENCY_ERROR
        )
        reason = summarize_pip_failure(stdout=stdout, stderr=stderr)

        return DependencyPreparationResult(
            working_directory=plan.working_directory,
            package_manager=plan.package_manager,
            command=command,
            success=False,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            failure_kind=failure_kind,
            error_message=f"'{' '.join(command)}' exited with code {exit_code}: {reason}",
            attempts=attempts,
        )

    @staticmethod
    def _build_command(plan: TestPlan) -> list[str] | None:
        manifest_name = Path(plan.dependency_manifest).name if plan.dependency_manifest else None

        if plan.package_manager == "pip":
            if manifest_name == "requirements.txt":
                return ["python", "-m", "pip", "install", "-r", "requirements.txt"]
            if manifest_name in {"pyproject.toml", "setup.py", "Pipfile"}:
                return ["python", "-m", "pip", "install", "."]
            return None

        if plan.package_manager == "npm":
            return ["npm", "install"]

        return None

    @staticmethod
    def _truncate(text: str) -> str:

        if len(text) <= MAX_TEST_OUTPUT_CHARS:
            return text

        half = MAX_TEST_OUTPUT_CHARS // 2
        omitted = len(text) - MAX_TEST_OUTPUT_CHARS

        return f"{text[:half]}\n... [{omitted} characters truncated] ...\n{text[-half:]}"
