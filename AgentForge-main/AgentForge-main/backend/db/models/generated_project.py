from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base


class GeneratedProjectRecord(Base):
    __tablename__ = "generated_projects"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.run_id"), primary_key=True)

    project_name: Mapped[str | None] = mapped_column(String(255), default=None)
    project_description: Mapped[str | None] = mapped_column(String, default=None)
    objective: Mapped[str | None] = mapped_column(String, default=None)
    status: Mapped[str] = mapped_column(String(32), default="new")

    backend_tech: Mapped[str | None] = mapped_column(String(255), default=None)
    frontend_tech: Mapped[str | None] = mapped_column(String(255), default=None)
    database_tech: Mapped[str | None] = mapped_column(String(255), default=None)
    deployment_tech: Mapped[str | None] = mapped_column(String(255), default=None)

    requirements: Mapped[list] = mapped_column(JSONB, default=list)
    tech_stack: Mapped[list] = mapped_column(JSONB, default=list)
    output_directory: Mapped[str | None] = mapped_column(String, default=None)
