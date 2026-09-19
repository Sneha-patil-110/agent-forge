from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class ProjectStatus(str, Enum):
    NEW = "new"
    ANALYZED = "analyzed"
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class ProjectState(BaseModel):
    project_name: str | None = Field(
        default=None,
        description="Name of the project.",
    )

    project_description: str | None = Field(
        default=None,
        description="Description of the project.",
    )

    objective: str | None = Field(
        default=None,
        description="Primary objective of the project.",
    )

    requirements: list[str] = Field(
        default_factory=list,
        description="Project requirements.",
    )

    backend: str | None = Field(
        default=None,
        description="Backend technology.",
    )

    frontend: str | None = Field(
        default=None,
        description="Frontend technology.",
    )

    database: str | None = Field(
        default=None,
        description="Database technology.",
    )

    deployment: str | None = Field(
        default=None,
        description="Deployment technology.",
    )

    target_audience: str | None = Field(
        default=None,
        description="Intended project audience.",
    )

    pending_clarifications: list[str] = Field(
        default_factory=list,
        description="Questions requiring user clarification.",
    )

    tech_stack: list[str] = Field(
        default_factory=list,
        description="Technologies used by the project.",
    )

    output_directory: str | None = Field(
        default=None,
        description=(
            "Root directory where generated project files "
            "may be written."
        ),
    )

    status: ProjectStatus = Field(
        default=ProjectStatus.NEW,
        description="Current project status.",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Project creation timestamp.",
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Most recent project update timestamp.",
    )