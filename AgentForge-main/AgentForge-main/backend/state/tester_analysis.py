from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from backend.state.execution_state import FailureCategory

_ALLOWED_TESTER_CLASSIFICATIONS = frozenset(
    {
        FailureCategory.APPLICATION_CODE_ERROR,
        FailureCategory.GENERATED_TEST_ERROR,
        FailureCategory.TEST_FAILURE,
    }
)


class TesterAnalysis(BaseModel):

    __test__ = False

    classification: FailureCategory | None = Field(
        default=None,
        description=(
            "APPLICATION_CODE_ERROR, GENERATED_TEST_ERROR, or TEST_FAILURE "
            "(ambiguous -- evidence didn't clearly indicate either). None only "
            "when there was nothing to analyze."
        ),
    )

    @field_validator("classification")
    @classmethod
    def _restrict_to_tester_owned_categories(
        cls, value: FailureCategory | None
    ) -> FailureCategory | None:
        if value is not None and value not in _ALLOWED_TESTER_CLASSIFICATIONS:
            allowed = ", ".join(sorted(c.value for c in _ALLOWED_TESTER_CLASSIFICATIONS))
            raise ValueError(
                f"Tester may only classify as one of: {allowed}. Got: {value.value!r}. "
                "Infrastructure categories are decided deterministically before Tester "
                "is ever invoked and can never be a real Tester conclusion."
            )
        return value

    summary: str | None = Field(
        default=None,
        description="Concise statement of what the failure evidence actually shows.",
    )

    affected_files: list[str] = Field(
        default_factory=list,
        description="Relative paths of files implicated by the failure -- application code or test files.",
    )

    evidence: str | None = Field(
        default=None,
        description=(
            "The specific comparison that grounds the classification, e.g. "
            "'Architecture specifies POST /users -> 201; implementation returns 201; "
            "test asserts 200.'"
        ),
    )

    recommended_action: str | None = Field(
        default=None,
        description="What Debugger/Developer should investigate or change next.",
    )

    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
