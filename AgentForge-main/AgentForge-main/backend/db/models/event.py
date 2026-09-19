from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class WorkflowEventRecord(Base):
    __tablename__ = "workflow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)

    event_type: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str | None] = mapped_column(String(32), default=None)
    message: Mapped[str | None] = mapped_column(String, default=None)
    event_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))