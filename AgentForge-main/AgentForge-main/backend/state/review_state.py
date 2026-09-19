from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ReviewIssue(BaseModel):
    title: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Concise title describing the issue.",
    )

    description: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Explanation of the issue and its impact.",
    )

    severity: Severity = Field(
        ...,
        description="Severity level of the issue.",
    )

    file_path: str | None = Field(
        default=None,
        description="Relative path of the affected generated file.",
    )

    suggestion: str | None = Field(
        default=None,
        max_length=500,
        description="Practical recommendation for resolving the issue.",
    )


class ReviewState(BaseModel):
    passed: bool = Field(
        default=False,
        description="Whether the implementation passed the review.",
    )

    score: float = Field(
        default=0.0,
        ge=0.0,
        le=10.0,
        description="Overall implementation quality score from 0 to 10.",
    )

    issues: list[ReviewIssue] = Field(
        default_factory=list,
        max_length=15,
        description="Evidence based issues identified during review.",
    )

    strengths: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="Positive aspects identified in the implementation.",
    )

    recommendations: list[str] = Field(
        default_factory=list,
        max_length=8,
        description="General recommendations for improving the implementation.",
    )

    review_summary: str | None = Field(
        default=None,
        max_length=1000,
        description="Concise summary of the implementation review.",
    )

    attempt_number: int = Field(
        default=0,
        ge=0,
        description="1-based genuine review attempt number for this run. System controlled -- overwritten by WorkflowNodes.reviewer(), never trusted from LLM output.",
    )

    auto_passed: bool = Field(
        default=False,
        description=(
            "True when the workflow proceeded to Documentation despite "
            "`passed=False`, because MAX_REVIEW_ATTEMPTS genuine review "
            "attempts were exhausted on non-critical findings. `passed` and "
            "every issue/score/summary field above stay exactly what "
            "Reviewer actually reported -- auto-passing never rewrites the "
            "real verdict, it only adds permission to proceed anyway. "
            "System controlled, same as attempt_number."
        ),
    )

    auto_pass_reason: str | None = Field(
        default=None,
        description="Set alongside auto_passed, e.g. 'review_attempt_limit_reached'.",
    )

    @model_validator(mode="after")
    def _validate_pass_consistency(self) -> ReviewState:
        if self.passed:
            if any(
                issue.severity == Severity.CRITICAL
                for issue in self.issues
            ):
                raise ValueError(
                    "`passed` cannot be true when a critical "
                    "severity issue exists."
                )

            if any(
                issue.severity == Severity.HIGH
                for issue in self.issues
            ):
                raise ValueError(
                    "`passed` cannot be true when an unresolved "
                    "high severity issue exists."
                )

        return self