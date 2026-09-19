from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


class KnowledgeCategory(str, Enum):
    ARCHITECTURE_DECISION = "architecture_decision"
    TECHNOLOGY_STACK = "technology_stack"
    PROJECT_CONVENTION = "project_convention"
    API_DECISION = "api_decision"
    DATABASE_DECISION = "database_decision"
    CODING_STANDARD = "coding_standard"
    ASSUMPTION = "assumption"
    KNOWN_LIMITATION = "known_limitation"
    COMPLETED_MILESTONE = "completed_milestone"


class KnowledgeStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class KnowledgeEntry(BaseModel):
    id: str = Field(..., description="Short unique identifier, stable for the life of the run.")

    category: KnowledgeCategory = Field(..., description="What kind of knowledge this is.")

    title: str = Field(..., description="Short, human readable summary.")

    content: str = Field(..., description="The knowledge itself.")

    created_by: str = Field(..., description="Name of the agent that recorded this entry.")

    status: KnowledgeStatus = Field(
        default=KnowledgeStatus.ACTIVE,
        description="ACTIVE entries are current; SUPERSEDED ones are kept for history only.",
    )

    source_id: str | None = Field(
        default=None,
        description=(
            "Identifier of the WorkflowState object this entry was derived "
            "from (e.g. an ArchitectureDecision or Task id), when there is "
            "one. Used to avoid recording the same fact twice."
        ),
    )

    supersedes: str | None = Field(
        default=None,
        description="id of the entry this one explicitly replaces, when applicable.",
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class KnowledgeState(BaseModel):
    entries: list[KnowledgeEntry] = Field(
        default_factory=list,
        description="Every knowledge entry recorded so far this workflow, active and superseded.",
    )