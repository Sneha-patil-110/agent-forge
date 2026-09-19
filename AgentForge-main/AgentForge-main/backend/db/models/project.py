from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class ProjectRecord(Base):

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, default=None
    )

    name: Mapped[str | None] = mapped_column(String(255), default=None)
    initial_prompt: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String(64), default="initialized")
    run_count: Mapped[int] = mapped_column(Integer, default=1)
    latest_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.run_id"), default=None
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
