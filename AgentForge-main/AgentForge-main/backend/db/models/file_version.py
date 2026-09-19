from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class FileVersionRecord(Base):
    __tablename__ = "file_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), index=True)
    path: Mapped[str] = mapped_column(String, index=True)

    content: Mapped[str] = mapped_column(String)
    source: Mapped[str] = mapped_column(String(16))
    edited_by: Mapped[str | None] = mapped_column(String(64), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
