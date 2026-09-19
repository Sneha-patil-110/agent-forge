from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.state.debug_state import DebugState, FailureCategory, SuggestedChange


def test_default_construction() -> None:
    state = DebugState()

    assert state.failure_category == FailureCategory.UNKNOWN
    assert state.confidence == 0.0
    assert state.affected_files == []
    assert state.suggested_changes == []


def test_json_round_trip() -> None:
    state = DebugState(
        failure_summary="A test failed.",
        root_cause="Missing validation.",
        failure_category=FailureCategory.CODE_DEFECT,
        affected_files=["calc.py"],
        repair_instructions="Add validation.",
        suggested_changes=[
            SuggestedChange(file_path="calc.py", description="Validate input.")
        ],
        confidence=0.8,
        attempt_number=1,
        debug_summary="Missing input validation.",
    )

    dumped = state.model_dump_json()
    restored = DebugState.model_validate_json(dumped)

    assert restored == state


def test_dict_round_trip() -> None:
    state = DebugState(failure_category=FailureCategory.DEPENDENCY_ISSUE)

    dumped = state.model_dump()
    restored = DebugState.model_validate(dumped)

    assert restored.model_dump() == dumped


def test_failure_category_enum_serializes_to_value() -> None:
    state = DebugState(failure_category=FailureCategory.ENVIRONMENT_ISSUE)

    assert state.model_dump()["failure_category"] == "environment_issue"


def test_empty_state_before_debugging_is_valid() -> None:
    state = DebugState()

    assert state.failure_summary is None
    assert state.root_cause is None


def test_one_finding_is_valid() -> None:
    state = DebugState(
        failure_summary="One issue.",
        root_cause="Root cause.",
        affected_files=["calc.py"],
    )

    assert len(state.affected_files) == 1


def test_multiple_suggested_changes_are_valid() -> None:
    state = DebugState(
        suggested_changes=[
            SuggestedChange(file_path="calc.py", description="Fix divide."),
            SuggestedChange(file_path="utils.py", description="Fix helper."),
        ]
    )

    assert len(state.suggested_changes) == 2


@pytest.mark.parametrize(
    "category",
    [
        FailureCategory.CODE_DEFECT,
        FailureCategory.TEST_DEFECT,
        FailureCategory.DEPENDENCY_ISSUE,
        FailureCategory.ENVIRONMENT_ISSUE,
        FailureCategory.CONFIGURATION_ISSUE,
        FailureCategory.UNKNOWN,
    ],
)
def test_all_failure_categories_are_valid(category: FailureCategory) -> None:
    state = DebugState(failure_category=category)

    assert state.failure_category == category


def test_rejects_invalid_failure_category() -> None:
    with pytest.raises(ValidationError):
        DebugState.model_validate({"failure_category": "not_a_real_category"})


def test_confidence_accepts_zero() -> None:
    state = DebugState(confidence=0.0)

    assert state.confidence == 0.0


def test_confidence_accepts_one() -> None:
    state = DebugState(confidence=1.0)

    assert state.confidence == 1.0


def test_confidence_rejects_below_zero() -> None:
    with pytest.raises(ValidationError):
        DebugState(confidence=-0.01)


def test_confidence_rejects_above_one() -> None:
    with pytest.raises(ValidationError):
        DebugState(confidence=1.01)


def test_rejects_negative_attempt_number() -> None:
    with pytest.raises(ValidationError):
        DebugState(attempt_number=-1)


def test_malformed_suggested_change_fails_clearly() -> None:
    with pytest.raises(ValidationError):
        DebugState.model_validate(
            {"suggested_changes": [{"file_path": "calc.py"}]}
        )

    with pytest.raises(ValidationError):
        DebugState.model_validate(
            {"suggested_changes": [{"description": "Fix it."}]}
        )
