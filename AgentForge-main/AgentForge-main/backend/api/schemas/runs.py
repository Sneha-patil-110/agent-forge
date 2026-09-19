from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    request: str = Field(..., min_length=1, description="Natural language description of the software to build.")


class RunAccepted(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    run_id: str
    project_id: str | None = None
    status: str
    current_step: str | None
    current_agent: str | None
    error_message: str | None
    test_retry_count: int
    review_retry_count: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class TestFailureSummary(BaseModel):
    name: str
    message: str | None = None
    file_path: str | None = None


class ReviewIssueSummary(BaseModel):
    title: str
    description: str
    severity: str
    file_path: str | None = None
    suggestion: str | None = None


class RunDetail(RunSummary):
    project_name: str | None
    dependency_retry_count: int = 0
    testing_result: str
    discovery_status: str | None = None
    tests_discovered: bool = False
    tests_executed: bool = False
    verification_method: str | None = None
    review_passed: bool
    review_score: float
    review_auto_passed: bool = False
    review_auto_pass_reason: str | None = None
    review_attempt_number: int = 0
    review_summary: str | None = None
    review_issues: list[ReviewIssueSummary] = Field(default_factory=list)
    files_materialized: int
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests_count: int = 0
    failed_test_names: list[TestFailureSummary] = Field(default_factory=list)
    failure_classification: str | None = None
    tester_summary: str | None = None


class RunList(BaseModel):
    runs: list[RunSummary]
    total_count: int
    has_more: bool