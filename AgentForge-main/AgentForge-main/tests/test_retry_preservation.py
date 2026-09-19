
from __future__ import annotations

from pathlib import Path

import pytest

from backend.services.run_service import RunService
from backend.state.execution_state import RepairTrigger, WorkflowStatus
from backend.state.testing_state import TestFailure
from backend.state.workflow_state import WorkflowState


@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


def test_test_retry_count_survives_persistence(run_service: RunService) -> None:
    metadata = run_service.create_run()

    state = run_service.load_state(metadata.run_id)
    state.execution.test_retry_count = 2
    state.execution.last_repair_trigger = RepairTrigger.TEST_FAILURE
    state.testing.failed_tests = [TestFailure(name="test_divide_by_zero")]
    run_service.save_state(metadata.run_id, state)

    reloaded = run_service.load_state(metadata.run_id)

    assert reloaded.execution.test_retry_count == 2
    assert reloaded.execution.last_repair_trigger == RepairTrigger.TEST_FAILURE
    assert reloaded.testing.failed_tests[0].name == "test_divide_by_zero"


def test_review_retry_count_survives_persistence_independently(
    run_service: RunService,
) -> None:
    metadata = run_service.create_run()

    state = run_service.load_state(metadata.run_id)
    state.execution.test_retry_count = 1
    state.execution.review_retry_count = 3
    state.execution.last_repair_trigger = RepairTrigger.REVIEW_FEEDBACK
    run_service.save_state(metadata.run_id, state)

    reloaded = run_service.load_state(metadata.run_id)

    assert reloaded.execution.test_retry_count == 1
    assert reloaded.execution.review_retry_count == 3
    assert reloaded.execution.last_repair_trigger == RepairTrigger.REVIEW_FEEDBACK


def test_failed_workflow_status_survives_persistence(run_service: RunService) -> None:
    metadata = run_service.create_run()

    state = run_service.load_state(metadata.run_id)
    state.execution.workflow_status = WorkflowStatus.FAILED
    state.execution.error_message = "Testing failed after the maximum number of retries (3)."
    run_service.save_state(metadata.run_id, state)

    reloaded = run_service.load_state(metadata.run_id)

    assert reloaded.execution.workflow_status == WorkflowStatus.FAILED
    assert "maximum number of retries" in reloaded.execution.error_message
