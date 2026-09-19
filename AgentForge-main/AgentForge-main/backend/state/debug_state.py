from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class FailureCategory(str, Enum):
    CODE_DEFECT = "code_defect"
    TEST_DEFECT = "test_defect"
    DEPENDENCY_ISSUE = "dependency_issue"
    ENVIRONMENT_ISSUE = "environment_issue"
    CONFIGURATION_ISSUE = "configuration_issue"
    UNKNOWN = "unknown"


class SuggestedChange(BaseModel):
    file_path: str = Field(
        ...,
        description="Relative path of the file that needs a change.",
    )

    description: str = Field(
        ...,
        description="What should change in this file and why.",
    )


class DebugState(BaseModel):

    failure_summary: str | None = Field(
        default=None,
        description="Concise description of what failed.",
    )

    root_cause: str | None = Field(
        default=None,
        description="Root cause of the failure.",
    )

    failure_category: FailureCategory = Field(
        default=FailureCategory.UNKNOWN,
        description="What kind of failure this is.",
    )

    affected_files: list[str] = Field(
        default_factory=list,
        description="Relative paths of files implicated by the failure.",
    )

    repair_instructions: str | None = Field(
        default=None,
        description="Actionable instructions for the Developer agent to apply.",
    )

    suggested_changes: list[SuggestedChange] = Field(
        default_factory=list,
        description="Specific per-file suggested changes.",
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Debugger's confidence in this analysis, from 0.0 to 1.0.",
    )

    attempt_number: int = Field(
        default=0,
        ge=0,
        description="1-based debugging attempt number for this failure chain.",
    )

    debug_summary: str | None = Field(
        default=None,
        description="Concise overall summary of the debugging analysis.",
    )
