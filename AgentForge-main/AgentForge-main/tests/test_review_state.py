from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.state.review_state import ReviewIssue, ReviewState, Severity


def test_empty_review_state_is_valid() -> None:
    state = ReviewState()

    assert state.passed is False


def test_passed_with_no_issues_is_valid() -> None:
    state = ReviewState(passed=True, score=9.0)

    assert state.passed is True


def test_passed_with_low_severity_issue_is_valid() -> None:
    state = ReviewState(
        passed=True,
        score=8.0,
        issues=[
            ReviewIssue(title="t", description="d", severity=Severity.LOW)
        ],
    )

    assert state.passed is True


def test_rejects_passed_with_critical_issue() -> None:
    with pytest.raises(ValidationError):
        ReviewState(
            passed=True,
            score=9.0,
            issues=[
                ReviewIssue(
                    title="t", description="d", severity=Severity.CRITICAL
                )
            ],
        )


def test_rejects_passed_with_high_issue() -> None:
    with pytest.raises(ValidationError):
        ReviewState(
            passed=True,
            score=8.0,
            issues=[
                ReviewIssue(
                    title="t", description="d", severity=Severity.HIGH
                )
            ],
        )


def test_rejects_score_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ReviewState(score=11.0)

    with pytest.raises(ValidationError):
        ReviewState(score=-1.0)


def test_failed_review_may_have_critical_issue() -> None:
    state = ReviewState(
        passed=False,
        score=1.0,
        issues=[
            ReviewIssue(
                title="t", description="d", severity=Severity.CRITICAL
            )
        ],
    )

    assert state.passed is False


def test_default_auto_pass_fields() -> None:
    state = ReviewState()

    assert state.attempt_number == 0
    assert state.auto_passed is False
    assert state.auto_pass_reason is None


def test_auto_passed_with_false_verdict_is_valid() -> None:
    state = ReviewState(
        passed=False,
        score=6.0,
        issues=[ReviewIssue(title="t", description="d", severity=Severity.LOW)],
        auto_passed=True,
        auto_pass_reason="review_attempt_limit_reached",
        attempt_number=2,
    )

    assert state.auto_passed is True
    assert state.passed is False
