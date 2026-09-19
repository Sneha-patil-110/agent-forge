from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RecoveryRecommendationOut(BaseModel):
    mode: str
    confidence: float
    explanation: str


class FailureDetailOut(BaseModel):
    run_id: str
    is_failed: bool
    failed_agent: str | None
    last_successful_agent: str | None
    failed_at: datetime | None
    test_retry_count: int
    review_retry_count: int
    error_message: str | None
    failure_category: str | None
    recovery_reason: str | None
    provider: str | None
    model: str | None
    duration_ms: int | None
    repeated_failure: bool
    last_checkpoint_id: str | None
    last_checkpoint_timestamp: str | None
    recommendation: RecoveryRecommendationOut | None


class CheckpointOut(BaseModel):
    checkpoint_id: str
    node_name: str | None
    timestamp: str | None


class CheckpointListOut(BaseModel):
    run_id: str
    checkpoints: list[CheckpointOut]


class TimelineEntryOut(BaseModel):
    agent: str
    attempt_number: int
    status: str
    duration_ms: int | None
    started_at: datetime | None
    completed_at: datetime | None
    provider: str | None
    model: str | None
    failure_category: str | None
    recovery_reason: str | None


class MCPCallOut(BaseModel):
    agent: str
    server_name: str
    tool_name: str
    success: bool
    duration_ms: float | None
    occurred_at: datetime


class TimelineOut(BaseModel):
    run_id: str
    entries: list[TimelineEntryOut]
    mcp_calls: list[MCPCallOut] = Field(default_factory=list)


class RestartFromCheckpointRequest(BaseModel):
    checkpoint_id: str = Field(..., min_length=1)


class RunLogsOut(BaseModel):
    run_id: str
    lines: list[str]
    truncated: bool
