from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class RunRecord(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True)

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, default=None
    )

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), index=True, default=None
    )
    request_text: Mapped[str | None] = mapped_column(String, default=None)

    status: Mapped[str] = mapped_column(String(64), default="initialized")
    current_step: Mapped[str | None] = mapped_column(String(255), default=None)
    current_agent: Mapped[str | None] = mapped_column(String(32), default=None)
    error_message: Mapped[str | None] = mapped_column(String, default=None)

    test_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    review_retry_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    state_json: Mapped[str | None] = mapped_column(
        Text,
        default=None,
        doc=(
            "Full WorkflowState JSON, mirrored here so a run survives the app "
            "container's ephemeral local disk being wiped on redeploy/restart."
        ),
    )
    run_metadata_json: Mapped[str | None] = mapped_column(
        Text,
        default=None,
        doc="Full RunMetadata JSON (ownership etc.), mirrored for the same reason as state_json.",
    )
    checkpoint_blob: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)