from __future__ import annotations

from datetime import UTC, datetime
from pydantic import BaseModel, Field


class RepairAttemptRecord(BaseModel):
    attempt_number: int = Field(..., description="1-based repair attempt count.")
    failure_fingerprint: str = Field(..., description="Deterministic fingerprint of the failure.")
    failure_category: str = Field(..., description="Category of failure.")
    debugger_diagnosis: str | None = Field(default=None, description="Debugger root cause summary.")
    files_targeted: list[str] = Field(default_factory=list, description="Files targeted for repair.")
    files_changed: list[str] = Field(default_factory=list, description="Files actually modified or added.")
    is_no_effect_repair: bool = Field(default=False, description="Whether repair produced zero code changes.")
    duration_seconds: float | None = Field(default=None, description="Duration of repair cycle.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
