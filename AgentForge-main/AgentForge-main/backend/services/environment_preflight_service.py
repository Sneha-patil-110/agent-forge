
from __future__ import annotations

import shutil
from pathlib import Path
from typing import NamedTuple

from backend.state.test_plan import TestPlan


class PreflightIssue(NamedTuple):
    code: str
    message: str


class PreflightResult(NamedTuple):
    passed: bool
    issues: list[PreflightIssue]


_RUNTIME_EXECUTABLES = {"python": "python", "node": "node"}
_PACKAGE_MANAGER_EXECUTABLES = {"pip": "python", "npm": "npm"}


class EnvironmentPreflightService:
    def check(
        self,
        *,
        project_root: str,
        integrity_passed: bool,
        plan: TestPlan,
    ) -> PreflightResult:
        issues: list[PreflightIssue] = []

        if not project_root:
            issues.append(PreflightIssue("NO_PROJECT_ROOT", "No project output directory is configured."))
            return PreflightResult(passed=False, issues=issues)

        root = Path(project_root)

        if not root.exists() or not root.is_dir():
            issues.append(
                PreflightIssue("PROJECT_ROOT_MISSING", f"Project root does not exist: {root}")
            )
            return PreflightResult(passed=False, issues=issues)

        if not integrity_passed:
            issues.append(
                PreflightIssue(
                    "REPOSITORY_INTEGRITY_NOT_PASSED",
                    "Repository integrity validation did not pass; skipping test execution.",
                )
            )
            return PreflightResult(passed=False, issues=issues)

        working_dir = root if plan.working_directory == "." else root / plan.working_directory

        if not working_dir.exists() or not working_dir.is_dir():
            issues.append(
                PreflightIssue(
                    "WORKING_DIRECTORY_MISSING",
                    f"Test working directory does not exist: {plan.working_directory}",
                )
            )
            return PreflightResult(passed=False, issues=issues)

        runtime_exe = _RUNTIME_EXECUTABLES.get(plan.runtime)
        if runtime_exe and shutil.which(runtime_exe) is None:
            issues.append(
                PreflightIssue(
                    "RUNTIME_UNAVAILABLE",
                    f"Required runtime '{plan.runtime}' ('{runtime_exe}') is not available on PATH.",
                )
            )

        if plan.package_manager:
            manager_exe = _PACKAGE_MANAGER_EXECUTABLES.get(plan.package_manager)
            if manager_exe and shutil.which(manager_exe) is None:
                issues.append(
                    PreflightIssue(
                        "PACKAGE_MANAGER_UNAVAILABLE",
                        f"Package manager '{plan.package_manager}' ('{manager_exe}') is not available on PATH.",
                    )
                )

            if not plan.dependency_manifest or not (root / plan.dependency_manifest).exists():
                issues.append(
                    PreflightIssue(
                        "DEPENDENCY_MANIFEST_MISSING",
                        f"Expected dependency manifest not found on disk: {plan.dependency_manifest}",
                    )
                )

        for stage in plan.stages:
            if not stage.command:
                continue
            executable = stage.command[0]
            if executable in {"python", "npm", "npx", "node"}:
                continue
            if shutil.which(executable) is None:
                issues.append(
                    PreflightIssue(
                        "TEST_COMMAND_UNAVAILABLE",
                        f"Configured test command executable '{executable}' is not available on PATH.",
                    )
                )

        return PreflightResult(passed=len(issues) == 0, issues=issues)
