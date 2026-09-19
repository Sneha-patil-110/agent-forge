from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.state.testing_state import DiscoveryStatus, TestFailure, TestingState, TestStatus


def test_default_construction() -> None:
    state = TestingState()

    assert state.status == TestStatus.NOT_RUN
    assert state.passed is False
    assert state.command is None
    assert state.failed_tests == []
    assert state.discovery_status is None
    assert state.tests_discovered is False
    assert state.tests_executed is False
    assert state.verification_method is None


def test_discovery_status_round_trips_through_json() -> None:
    state = TestingState(
        status=TestStatus.PASSED,
        passed=True,
        discovery_status=DiscoveryStatus.RECOGNIZED_NO_TESTS,
        tests_discovered=False,
        tests_executed=False,
        verification_method="compile_check",
    )

    restored = TestingState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert restored.discovery_status == DiscoveryStatus.RECOGNIZED_NO_TESTS


def test_json_round_trip() -> None:
    state = TestingState(
        status=TestStatus.FAILED,
        command=["python", "-m", "pytest"],
        exit_code=1,
        stdout="output",
        stderr="error",
        passed=False,
        failed_tests=[TestFailure(name="test_x", message="boom")],
        duration_seconds=1.5,
        attempt_number=2,
    )

    dumped = state.model_dump_json()
    restored = TestingState.model_validate_json(dumped)

    assert restored == state


def test_dict_round_trip() -> None:
    state = TestingState(status=TestStatus.PASSED, passed=True)

    dumped = state.model_dump()
    restored = TestingState.model_validate(dumped)

    assert restored.model_dump() == dumped


def test_status_enum_serializes_to_value() -> None:
    state = TestingState(status=TestStatus.TIMEOUT)

    assert state.model_dump()["status"] == "timeout"


def test_empty_pre_execution_state_is_valid() -> None:
    state = TestingState()

    assert state.status == TestStatus.NOT_RUN
    assert state.exit_code is None


def test_passed_state_is_valid() -> None:
    state = TestingState(
        status=TestStatus.PASSED,
        passed=True,
        exit_code=0,
        total_tests=3,
        passed_tests=3,
    )

    assert state.passed is True


def test_failed_state_is_valid() -> None:
    state = TestingState(
        status=TestStatus.FAILED,
        passed=False,
        exit_code=1,
        failed_tests=[TestFailure(name="test_x")],
    )

    assert state.passed is False
    assert len(state.failed_tests) == 1


def test_error_state_is_valid() -> None:
    state = TestingState(
        status=TestStatus.ERROR,
        error_type="command_rejected",
        testing_summary="Command not allowed.",
    )

    assert state.status == TestStatus.ERROR


def test_timeout_state_is_valid() -> None:
    state = TestingState(
        status=TestStatus.TIMEOUT,
        timed_out=True,
        error_type="timeout",
    )

    assert state.timed_out is True


def test_rejects_passed_true_with_failed_status() -> None:
    with pytest.raises(ValidationError):
        TestingState(status=TestStatus.FAILED, passed=True)


def test_rejects_passed_true_with_nonempty_failed_tests() -> None:
    with pytest.raises(ValidationError):
        TestingState(
            status=TestStatus.PASSED,
            passed=True,
            failed_tests=[TestFailure(name="test_x")],
        )


def test_rejects_counts_exceeding_total() -> None:
    with pytest.raises(ValidationError):
        TestingState(
            total_tests=2,
            passed_tests=2,
            failed_tests=[TestFailure(name="test_x")],
        )


def test_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        TestingState(total_tests=-1)

    with pytest.raises(ValidationError):
        TestingState(passed_tests=-1)

    with pytest.raises(ValidationError):
        TestingState(skipped_tests=-1)


def test_rejects_negative_duration() -> None:
    with pytest.raises(ValidationError):
        TestingState(duration_seconds=-0.1)


def test_rejects_negative_attempt_number() -> None:
    with pytest.raises(ValidationError):
        TestingState(attempt_number=-1)


def test_rejects_invalid_status_value() -> None:
    with pytest.raises(ValidationError):
        TestingState.model_validate({"status": "not_a_real_status"})


def test_allows_passed_false_with_critical_status_regardless_of_counts() -> None:
    state = TestingState(status=TestStatus.ERROR, passed=False)

    assert state.total_tests == 0
