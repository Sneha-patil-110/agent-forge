from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class MCPExecutionRecord(Base):
    __tablename__ = "mcp_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    agent: Mapped[str] = mapped_column(String(32))
    server_name: Mapped[str] = mapped_column(String(64))
    tool_name: Mapped[str] = mapped_column(String(128))
    success: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error_message: Mapped[str | None] = mapped_column(String, default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_mcp_executions_server_success", "server_name", "success"),
        Index("ix_mcp_executions_agent", "agent"),
    )
