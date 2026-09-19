from __future__ import annotations

from pathlib import Path

from backend.services.failure_bundle_service import FailureBundleService
from backend.services.repository_integrity_validator import RepositoryIntegrityValidator
from backend.services.run_service import RunService
from backend.state.execution_state import FailureCategory, WorkflowStatus
from backend.state.workflow_state import WorkflowState



def test_content_hash_is_stable_for_identical_content(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")

    validator = RepositoryIntegrityValidator()
    snap1 = validator.create_snapshot(str(tmp_path))
    snap2 = validator.create_snapshot(str(tmp_path))

    assert snap1.content_hash == snap2.content_hash
    assert snap1.content_hash is not None


def test_content_hash_changes_when_file_content_changes(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    validator = RepositoryIntegrityValidator()
    before = validator.create_snapshot(str(tmp_path))

    (tmp_path / "main.py").write_text("x = 2\n", encoding="utf-8")
    after = validator.create_snapshot(str(tmp_path))

    assert before.content_hash != after.content_hash


def test_content_hash_changes_when_a_file_is_added(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    validator = RepositoryIntegrityValidator()
    before = validator.create_snapshot(str(tmp_path))

    (tmp_path / "extra.py").write_text("y = 2\n", encoding="utf-8")
    after = validator.create_snapshot(str(tmp_path))

    assert before.content_hash != after.content_hash



def test_should_not_persist_for_a_clean_completed_run() -> None:
    state = WorkflowState()
    state.execution.workflow_status = WorkflowStatus.COMPLETED

    assert FailureBundleService().should_persist(state) is False


def test_should_persist_for_failed_and_verification_issues_runs() -> None:
    service = FailureBundleService()

    failed_state = WorkflowState()
    failed_state.execution.workflow_status = WorkflowStatus.FAILED
    assert service.should_persist(failed_state) is True

    partial_state = WorkflowState()
    partial_state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert service.should_persist(partial_state) is True


def test_build_captures_real_evidence_not_fabricated() -> None:
    state = WorkflowState()
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.testing.classification = FailureCategory.GENERATED_TEST_ERROR
    state.testing.failed_tests = []
    state.execution.test_retry_count = 2
    state.project.project_name = "Test Project"

    bundle = FailureBundleService().build(run_id="af_test123", state=state)

    assert bundle.run_id == "af_test123"
    assert bundle.workflow_status == WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    assert bundle.failure_classification == FailureCategory.GENERATED_TEST_ERROR
    assert bundle.test_retry_count == 2
    assert bundle.project.project_name == "Test Project"



def test_save_and_load_failure_bundle_round_trips(tmp_path: Path) -> None:
    run_service = RunService(runs_root=tmp_path)
    metadata = run_service.create_run()

    state = WorkflowState()
    state.execution.workflow_status = WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES
    state.testing.classification = FailureCategory.DEPENDENCY_INSTALL_ERROR

    bundle = FailureBundleService().build(run_id=metadata.run_id, state=state)
    run_service.save_failure_bundle(metadata.run_id, bundle)

    loaded = run_service.load_failure_bundle(metadata.run_id)

    assert loaded is not None
    assert loaded.run_id == metadata.run_id
    assert loaded.failure_classification == FailureCategory.DEPENDENCY_INSTALL_ERROR


def test_load_failure_bundle_returns_none_when_never_persisted(tmp_path: Path) -> None:
    run_service = RunService(runs_root=tmp_path)
    metadata = run_service.create_run()

    assert run_service.load_failure_bundle(metadata.run_id) is None
