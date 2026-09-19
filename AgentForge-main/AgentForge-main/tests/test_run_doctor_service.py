from __future__ import annotations

from backend.services.run_doctor_service import RunDoctorService
from backend.state.execution_state import FailureCategory, WorkflowStatus
from backend.state.repository_snapshot import RepositorySnapshot
from backend.state.testing_state import TestFailure
from backend.state.workflow_state import WorkflowState


def test_fully_passed_run_shows_all_stages_pass() -> None:
    state = WorkflowState()
    state.testing.passed = True
    state.testing.total_tests = 5
    state.testing.passed_tests = 5
    state.implementation.written_files = ["main.py"]
    state.repository_snapshot = RepositorySnapshot(project_root="/x", file_tree=["main.py"])
    state.execution.workflow_status = WorkflowStatus.COMPLETED

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    assert all(stage.status == "PASS" for stage in report.stages)
    assert report.terminal_reason == "VERIFIED"
    assert report.classification is None


def test_static_validation_failure_stops_before_discovery() -> None:
    state = WorkflowState()
    state.implementation.written_files = ["main.py"]
    state.testing.classification = FailureCategory.STATIC_VALIDATION_ERROR
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.execution.current_step = "Static validation retry limit exceeded"

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    stage_map = dict(report.stages)
    assert stage_map["Static validation"] == "FAIL"
    assert stage_map["Test discovery"] == "SKIP"
    assert stage_map["Environment preflight"] == "SKIP"
    assert stage_map["Dependency preparation"] == "SKIP"
    assert stage_map["Test execution"] == "SKIP"
    assert "Application tests" not in stage_map
    assert report.terminal_reason == "VERIFICATION_REPAIR_EXHAUSTED"


def test_discovery_failure_stops_before_preflight() -> None:
    state = WorkflowState()
    state.implementation.written_files = ["main.py"]
    state.testing.classification = FailureCategory.TEST_DISCOVERY_ERROR
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    stage_map = dict(report.stages)
    assert stage_map["Static validation"] == "PASS"
    assert stage_map["Test discovery"] == "FAIL"
    assert stage_map["Environment preflight"] == "SKIP"
    assert report.terminal_reason == "INFRASTRUCTURE_FAILURE"


def test_dependency_failure_stops_before_test_execution() -> None:
    state = WorkflowState()
    state.implementation.written_files = ["main.py"]
    state.testing.classification = FailureCategory.DEPENDENCY_INSTALL_ERROR
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    stage_map = dict(report.stages)
    assert stage_map["Test discovery"] == "PASS"
    assert stage_map["Environment preflight"] == "PASS"
    assert stage_map["Dependency preparation"] == "FAIL"
    assert stage_map["Test execution"] == "SKIP"
    assert report.terminal_reason == "INFRASTRUCTURE_FAILURE"


def test_real_application_code_failure_reaches_application_tests_stage() -> None:
    state = WorkflowState()
    state.implementation.written_files = ["main.py"]
    state.testing.classification = FailureCategory.APPLICATION_CODE_ERROR
    state.testing.passed = False
    state.testing.total_tests = 5
    state.testing.passed_tests = 3
    state.testing.failed_tests = [TestFailure(name="test_x", message="boom")]
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.execution.current_step = "Test retry limit exceeded"

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    stage_map = dict(report.stages)
    assert stage_map["Test execution"] == "PASS"
    assert stage_map["Application tests"] == "FAIL"
    assert report.passed_tests == 3
    assert report.failed_tests == 1
    assert report.terminal_reason == "VERIFICATION_REPAIR_EXHAUSTED"


def test_generated_test_error_is_distinguishable_from_application_code_error() -> None:
    state = WorkflowState()
    state.implementation.written_files = ["main.py"]
    state.testing.classification = FailureCategory.GENERATED_TEST_ERROR
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    assert report.classification == FailureCategory.GENERATED_TEST_ERROR
    stage_map = dict(report.stages)
    assert stage_map["Application tests"] == "FAIL"


def test_no_effect_repair_terminal_reason() -> None:
    state = WorkflowState()
    state.implementation.written_files = ["main.py"]
    state.testing.classification = FailureCategory.APPLICATION_CODE_ERROR
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.execution.current_step = "Identical test failure persisted with no code changes"

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    assert report.terminal_reason == "NO_EFFECT_REPAIR"


def test_never_reached_test_pipeline_shows_skip_not_fail() -> None:

    state = WorkflowState()
    state.execution.workflow_status = WorkflowStatus.FAILED

    report = RunDoctorService().diagnose(run_id="af_x", state=state)

    stage_map = dict(report.stages)
    assert stage_map["Repository generation"] == "FAIL"
    assert stage_map["Static validation"] == "SKIP"
    assert stage_map["Test discovery"] == "SKIP"
    assert report.terminal_reason == "GENERATION_FAILED"
