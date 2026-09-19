from __future__ import annotations

from pathlib import Path

from backend.services.environment_preflight_service import EnvironmentPreflightService
from backend.state.test_plan import TestPlan, TestStage


def _plan(**overrides) -> TestPlan:
    defaults = dict(
        framework="pytest",
        runtime="python",
        working_directory=".",
        stages=[TestStage(name="full_suite", command=["python", "-m", "pytest"])],
        targeted_test_capability=True,
        test_files=["test_x.py"],
        configuration_files=[],
        dependency_manifest="requirements.txt",
        package_manager="pip",
    )
    defaults.update(overrides)
    return TestPlan(**defaults)


def test_passes_for_a_real_valid_project(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    service = EnvironmentPreflightService()
    result = service.check(project_root=str(tmp_path), integrity_passed=True, plan=_plan())

    assert result.passed is True
    assert result.issues == []


def test_fails_for_missing_project_root() -> None:
    service = EnvironmentPreflightService()
    result = service.check(project_root="", integrity_passed=True, plan=_plan())

    assert result.passed is False
    assert result.issues[0].code == "NO_PROJECT_ROOT"


def test_fails_when_repository_integrity_did_not_pass(tmp_path: Path) -> None:
    service = EnvironmentPreflightService()
    result = service.check(project_root=str(tmp_path), integrity_passed=False, plan=_plan())

    assert result.passed is False
    assert result.issues[0].code == "REPOSITORY_INTEGRITY_NOT_PASSED"


def test_fails_for_invalid_working_directory(tmp_path: Path) -> None:
    service = EnvironmentPreflightService()
    plan = _plan(working_directory="backend")

    result = service.check(project_root=str(tmp_path), integrity_passed=True, plan=plan)

    assert result.passed is False
    assert result.issues[0].code == "WORKING_DIRECTORY_MISSING"


def test_fails_for_missing_runtime(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    service = EnvironmentPreflightService()
    plan = _plan(runtime="a-runtime-that-does-not-exist")

    result = service.check(project_root=str(tmp_path), integrity_passed=True, plan=plan)

    assert result.passed is True


def test_fails_for_missing_dependency_manifest_on_disk(tmp_path: Path) -> None:
    service = EnvironmentPreflightService()
    plan = _plan(dependency_manifest="requirements.txt", package_manager="pip")

    result = service.check(project_root=str(tmp_path), integrity_passed=True, plan=plan)

    assert result.passed is False
    assert any(issue.code == "DEPENDENCY_MANIFEST_MISSING" for issue in result.issues)


def test_fails_for_unavailable_configured_test_command(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    service = EnvironmentPreflightService()
    plan = _plan(
        stages=[TestStage(name="full_suite", command=["a-command-that-does-not-exist-anywhere"])]
    )

    result = service.check(project_root=str(tmp_path), integrity_passed=True, plan=plan)

    assert result.passed is False
    assert any(issue.code == "TEST_COMMAND_UNAVAILABLE" for issue in result.issues)


def test_passes_for_project_with_no_dependency_manifest(tmp_path: Path) -> None:
    service = EnvironmentPreflightService()
    plan = _plan(dependency_manifest=None, package_manager=None)

    result = service.check(project_root=str(tmp_path), integrity_passed=True, plan=plan)

    assert result.passed is True
