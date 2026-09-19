from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.state.execution_state import AgentType


class EventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_RESUMED = "workflow_resumed"

    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"

    TESTING_PASSED = "testing_passed"
    TESTING_FAILED = "testing_failed"

    REVIEW_PASSED = "review_passed"
    REVIEW_FAILED = "review_failed"

    REVIEWER_ATTEMPT_STARTED = "reviewer_attempt_started"
    REVIEWER_ATTEMPT_COMPLETED = "reviewer_attempt_completed"
    REVIEWER_REPAIR_REQUESTED = "reviewer_repair_requested"
    REVIEWER_AUTO_PASSED = "reviewer_auto_passed"

    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_COMPLETED_WITH_VERIFICATION_ISSUES = "workflow_completed_with_verification_issues"
    WORKFLOW_INTERRUPTED = "workflow_interrupted"
    WORKFLOW_FAILED = "workflow_failed"

    MCP_TOOL_CALL_STARTED = "mcp_tool_call_started"
    MCP_TOOL_CALL_COMPLETED = "mcp_tool_call_completed"
    MCP_TOOL_CALL_FAILED = "mcp_tool_call_failed"
    MCP_TOOL_CALL_RECORDED = "mcp_tool_call_recorded"

    FILE_CREATED = "file_created"
    FILE_MODIFIED = "file_modified"
    FILE_DELETED = "file_deleted"
    FILE_RENAMED = "file_renamed"
    FOLDER_CREATED = "folder_created"
    FOLDER_DELETED = "folder_deleted"
    DOCUMENTATION_GENERATED = "documentation_generated"

    AGENT_INVOCATION_RECORDED = "agent_invocation_recorded"
    RECOVERY_ACTION_TAKEN = "recovery_action_taken"

    REPOSITORY_MATERIALIZED = "repository_materialized"
    REPOSITORY_INTEGRITY_STARTED = "repository_integrity_started"
    REPOSITORY_INTEGRITY_PASSED = "repository_integrity_passed"
    REPOSITORY_INTEGRITY_FAILED = "repository_integrity_failed"
    REPOSITORY_SNAPSHOT_CREATED = "repository_snapshot_created"
    TESTER_CONTEXT_CREATED = "tester_context_created"



class WorkflowEvent(BaseModel):

    event_type: EventType
    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: AgentType | None = Field(
        default=None,
        description="Agent this event concerns, when applicable.",
    )
    message: str | None = Field(
        default=None,
        description="Short, human readable summary of what happened.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Small structured extras only; never prompts, "
        "responses, source code, or secrets.",
    )
