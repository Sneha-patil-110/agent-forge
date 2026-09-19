from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class AgentInvocationRecord(Base):
    __tablename__ = "agent_invocations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    repair_trigger: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str] = mapped_column(String(16))

    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    model: Mapped[str | None] = mapped_column(String(64), default=None)
    provider_request_id: Mapped[str | None] = mapped_column(String(128), default=None)

    input_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    output_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    prompt_characters: Mapped[int | None] = mapped_column(Integer, default=None)
    response_characters: Mapped[int | None] = mapped_column(Integer, default=None)

    exception_type: Mapped[str | None] = mapped_column(String(255), default=None)
    failure_category: Mapped[str | None] = mapped_column(String(64), default=None)
    recovery_reason: Mapped[str | None] = mapped_column(String(32), default=None)
    error_message: Mapped[str | None] = mapped_column(String, default=None)
    stacktrace: Mapped[str | None] = mapped_column(String, default=None)
    checkpoint_id: Mapped[str | None] = mapped_column(String(128), default=None)

    duration_ms: Mapped[int | None] = mapped_column(Integer, default=None)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    __table_args__ = (
        Index("ix_agent_invocations_agent_status", "agent", "status"),
    )
