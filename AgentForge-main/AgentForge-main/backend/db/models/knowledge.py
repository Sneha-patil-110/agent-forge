from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class KnowledgeEntryRecord(Base):
    __tablename__ = "knowledge_entries"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), primary_key=True, index=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    category: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(String)
    created_by: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active")
    source_id: Mapped[str | None] = mapped_column(String(255), default=None)
    supersedes: Mapped[str | None] = mapped_column(String(255), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))