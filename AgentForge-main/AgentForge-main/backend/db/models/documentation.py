from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class DocumentationRecord(Base):

    __tablename__ = "documentation_files"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), primary_key=True, index=True)
    path: Mapped[str] = mapped_column(String, primary_key=True)

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String, default=None)
    generating_agent: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
