from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.replay_service import RepositoryNoLongerOnDiskError, ReplayService
from backend.services.repository_integrity_validator import RepositoryIntegrityValidator
from backend.services.run_service import RunService
from backend.state.execution_state import FailureCategory, WorkflowStatus
from backend.state.testing_state import TestStatus
from backend.state.workflow_state import WorkflowState


def _seed_original_run(run_service: RunService, output_directory: Path, *, snapshot=None) -> str:
    metadata = run_service.create_run()
    state = WorkflowState()
    state.project.output_directory = str(output_directory)
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.testing.classification = FailureCategory.APPLICATION_CODE_ERROR
    state.testing.status = TestStatus.FAILED
    state.repository_snapshot = snapshot
    run_service.save_state(metadata.run_id, state)
    return metadata.run_id


def _passing_tester_node(state: WorkflowState) -> WorkflowState:
    state.testing.passed = True
    state.testing.status = TestStatus.PASSED
    state.testing.classification = None
    return state


def test_replay_creates_a_new_run_and_never_touches_the_original(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()
    (output_directory / "main.py").write_text("x = 1\n", encoding="utf-8")

    run_service = RunService(runs_root=tmp_path / "runs")
    validator = RepositoryIntegrityValidator()
    original_snapshot = validator.create_snapshot(str(output_directory))

    original_run_id = _seed_original_run(run_service, output_directory, snapshot=original_snapshot)
    original_state_before = run_service.load_state(original_run_id)

    service = ReplayService(
        run_service=run_service,
        repository_integrity_validator=validator,
        tester_node=_passing_tester_node,
    )

    result = service.replay_from_testing(original_run_id)

    assert result.replay_run_id != original_run_id
    assert result.state.testing.passed is True
    assert result.hash_mismatch_warning is None

    original_state_after = run_service.load_state(original_run_id)
    assert original_state_after == original_state_before
    assert original_state_after.execution.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES

    replay_state = run_service.load_state(result.replay_run_id)
    assert replay_state.testing.passed is True


def test_replay_surfaces_a_warning_when_repository_content_has_changed(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()
    (output_directory / "main.py").write_text("x = 1\n", encoding="utf-8")

    run_service = RunService(runs_root=tmp_path / "runs")
    validator = RepositoryIntegrityValidator()
    stale_snapshot = validator.create_snapshot(str(output_directory))

    original_run_id = _seed_original_run(run_service, output_directory, snapshot=stale_snapshot)

    (output_directory / "main.py").write_text("x = 2\n", encoding="utf-8")

    service = ReplayService(
        run_service=run_service,
        repository_integrity_validator=validator,
        tester_node=_passing_tester_node,
    )

    result = service.replay_from_testing(original_run_id)

    assert result.hash_mismatch_warning is not None
    assert "no longer matches" in result.hash_mismatch_warning


def test_replay_raises_when_repository_no_longer_exists(tmp_path: Path) -> None:
    run_service = RunService(runs_root=tmp_path / "runs")
    validator = RepositoryIntegrityValidator()

    missing_dir = tmp_path / "does-not-exist"
    original_run_id = _seed_original_run(run_service, missing_dir)

    service = ReplayService(
        run_service=run_service,
        repository_integrity_validator=validator,
        tester_node=_passing_tester_node,
    )

    with pytest.raises(RepositoryNoLongerOnDiskError):
        service.replay_from_testing(original_run_id)


def test_replay_resets_retry_count_and_status_before_invoking_tester(tmp_path: Path) -> None:
    output_directory = tmp_path / "project"
    output_directory.mkdir()
    (output_directory / "main.py").write_text("x = 1\n", encoding="utf-8")

    run_service = RunService(runs_root=tmp_path / "runs")
    validator = RepositoryIntegrityValidator()
    snapshot = validator.create_snapshot(str(output_directory))

    metadata = run_service.create_run()
    state = WorkflowState()
    state.project.output_directory = str(output_directory)
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.execution.test_retry_count = 3
    state.execution.error_message = "previous failure"
    state.repository_snapshot = snapshot
    run_service.save_state(metadata.run_id, state)

    seen_state: dict = {}

    def _capturing_tester_node(s: WorkflowState) -> WorkflowState:
        seen_state["test_retry_count"] = s.execution.test_retry_count
        seen_state["workflow_status"] = s.execution.workflow_status
        seen_state["error_message"] = s.execution.error_message
        return s

    service = ReplayService(
        run_service=run_service,
        repository_integrity_validator=validator,
        tester_node=_capturing_tester_node,
    )

    service.replay_from_testing(metadata.run_id)

    assert seen_state["test_retry_count"] == 0
    assert seen_state["workflow_status"] == WorkflowStatus.RUNNING
    assert seen_state["error_message"] is None
