from __future__ import annotations

from pydantic import BaseModel


class AgentStatsOut(BaseModel):
    agent: str
    total: int
    success_count: int
    failure_count: int
    success_rate: float
    avg_duration_ms: float | None
    avg_input_tokens: float | None
    avg_output_tokens: float | None


class ReliabilitySummaryOut(BaseModel):
    overall_total: int
    overall_success_count: int
    overall_success_rate: float
    per_agent: list[AgentStatsOut]
    failure_category_breakdown: dict[str, int]
    recovery_reason_breakdown: dict[str, int]
    provider_breakdown: dict[str, int]


class AgentFailureOut(BaseModel):
    run_id: str
    attempt_number: int
    status: str
    exception_type: str | None
    failure_category: str | None
    recovery_reason: str | None
    error_message: str | None
    provider: str | None
    model: str | None
    duration_ms: int | None


class AgentDetailOut(BaseModel):
    agent: str
    stats: AgentStatsOut | None
    recovery_reason_breakdown: dict[str, int]
    recent_failures: list[AgentFailureOut]
