
from __future__ import annotations

from backend.services.dependency_preparation_service import DependencyPreparationResult
from backend.services.environment_preflight_service import PreflightResult
from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.test_plan import TestPlan, TestStage
from backend.state.testing_state import TestingState, TestStatus


def make_stub_test_plan(
    *,
    framework: str = "pytest",
    working_directory: str = ".",
    targeted_test_capability: bool = True,
) -> TestPlan:
    return TestPlan(
        framework=framework,
        runtime="python",
        working_directory=working_directory,
        stages=[TestStage(name="full_suite", command=["pytest"])],
        targeted_test_capability=targeted_test_capability,
        test_files=["test_stub.py"],
        configuration_files=[],
        dependency_manifest="requirements.txt",
        package_manager="pip",
    )


class StubTestDiscoveryService:
    def __init__(self, plans: list[TestPlan] | None = None) -> None:
        self._plans = plans if plans is not None else [make_stub_test_plan()]

    def discover(self, snapshot: RepositorySnapshot) -> list[TestPlan]:
        return self._plans


class StubEnvironmentPreflightService:
    def __init__(self, passed: bool = True) -> None:
        self.passed = passed

    def check(self, *, project_root, integrity_passed, plan) -> PreflightResult:
        if self.passed:
            return PreflightResult(passed=True, issues=[])
        from backend.services.environment_preflight_service import PreflightIssue

        return PreflightResult(passed=False, issues=[PreflightIssue("STUB_FAILURE", "Stubbed preflight failure.")])


class StubDependencyPreparationService:
    def __init__(self, success: bool = True) -> None:
        self.success = success

    def prepare(self, *, project_root, plan) -> DependencyPreparationResult:
        if self.success:
            return DependencyPreparationResult(working_directory=plan.working_directory, skipped=True)
        return DependencyPreparationResult(
            working_directory=plan.working_directory,
            package_manager=plan.package_manager,
            success=False,
            error_message="Stubbed dependency installation failure.",
        )


class StubRepositoryIntegrityValidator:

    def create_snapshot(self, output_directory, state=None) -> RepositorySnapshot:
        return RepositorySnapshot(
            project_root=output_directory or "stub",
            file_tree=["test_stub.py", "requirements.txt"],
            top_level_directories=[],
            project_type="python",
        )

    def validate_repository(self, output_directory, *, state=None, written_files=None, raise_on_error=False):
        from backend.services.repository_integrity_validator import IntegrityCheckResult

        return IntegrityCheckResult(is_valid=True, issues=[])


class StubTestingService:

    def __init__(self, passed: bool) -> None:
        self.passed = passed

    def execute_stage(self, *, project, plan, stage, attempt_number, targeted_tests=None) -> TestingState:
        return TestingState(
            status=TestStatus.PASSED if self.passed else TestStatus.FAILED,
            command=stage.command,
            passed=self.passed,
            attempt_number=attempt_number,
        )
