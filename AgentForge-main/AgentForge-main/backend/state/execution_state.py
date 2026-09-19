from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    INITIALIZED = "initialized"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    COMPLETED = "completed"
    COMPLETED_WITH_VERIFICATION_ISSUES = "completed_with_verification_issues"
    FAILED = "failed"


class AgentType(str, Enum):
    ANALYSIS = "analysis"
    PLANNER = "planner"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    STATIC_VALIDATION = "static_validation"
    TESTER = "tester"
    DEBUGGER = "debugger"
    REVIEWER = "reviewer"
    DOCUMENTATION = "documentation"


class RepairTrigger(str, Enum):

    NONE = "none"
    TEST_FAILURE = "test_failure"
    REVIEW_FEEDBACK = "review_feedback"
    STATIC_VALIDATION_FAILURE = "static_validation_failure"
    REPOSITORY_COMPLETENESS_FAILURE = "repository_completeness_failure"
    DEPENDENCY_RESOLUTION_FAILURE = "dependency_resolution_failure"


class FailureCategory(str, Enum):

    LLM_GENERATION_ERROR = "llm_generation_error"
    ARTIFACT_SCHEMA_ERROR = "artifact_schema_error"
    PATH_VALIDATION_ERROR = "path_validation_error"
    MATERIALIZATION_ERROR = "materialization_error"
    REPOSITORY_INTEGRITY_ERROR = "repository_integrity_error"
    STATIC_VALIDATION_ERROR = "static_validation_error"
    DEPENDENCY_INSTALL_ERROR = "dependency_install_error"
    TEST_DISCOVERY_ERROR = "test_discovery_error"
    REPOSITORY_COMPLETENESS_ERROR = "repository_completeness_error"
    DEPENDENCY_RESOLUTION_ERROR = "dependency_resolution_error"
    ENVIRONMENT_ERROR = "environment_error"
    TEST_EXECUTION_ERROR = "test_execution_error"
    TEST_TIMEOUT = "test_timeout"
    APPLICATION_CODE_ERROR = "application_code_error"
    GENERATED_TEST_ERROR = "generated_test_error"
    AGENT_OUTPUT_SCHEMA_ERROR = "agent_output_schema_error"
    TEST_FAILURE = "test_failure"
    MCP_ERROR = "mcp_error"
    PROVIDER_ERROR = "provider_error"


INFRASTRUCTURE_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.DEPENDENCY_INSTALL_ERROR,
        FailureCategory.TEST_DISCOVERY_ERROR,
        FailureCategory.ENVIRONMENT_ERROR,
        FailureCategory.TEST_EXECUTION_ERROR,
        FailureCategory.TEST_TIMEOUT,
        FailureCategory.AGENT_OUTPUT_SCHEMA_ERROR,
        FailureCategory.PROVIDER_ERROR,
        FailureCategory.MCP_ERROR,
    }
)



class ExecutionState(BaseModel):
    workflow_status: WorkflowStatus = Field(
        default=WorkflowStatus.INITIALIZED,
        description="Current workflow execution status.",
    )

    current_agent: AgentType | None = Field(
        default=None,
        description="Agent currently executing.",
    )

    current_step: str | None = Field(
        default=None,
        description="Current execution step.",
    )

    review_retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of times the workflow has returned from Reviewer to Developer.",
    )

    test_retry_count: int = Field(
        default=0,
        ge=0,
        description="Number of times the workflow has returned from Tester to Debugger.",
    )

    dependency_retry_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of times a genuine (non-transient) dependency-resolution "
            "failure has routed to Debugger for a manifest repair. Deliberately "
            "separate from test_retry_count -- a broken requirements.txt and a "
            "broken test are unrelated repair budgets."
        ),
    )

    last_repair_trigger: RepairTrigger = Field(
        default=RepairTrigger.NONE,
        description="Why Developer is being re-invoked: test failure, review feedback, or neither.",
    )

    repair_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Recorded history of repair attempts and outcomes.",
    )

    error_message: str | None = Field(
        default=None,
        description="Latest execution error.",
    )

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
    )

    completed_at: datetime | None = Field(
        default=None,
        description="Time at which workflow execution completed.",
    )
