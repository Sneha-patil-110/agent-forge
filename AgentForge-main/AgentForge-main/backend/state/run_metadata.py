
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

RUN_METADATA_SCHEMA_VERSION = 1


class RunMetadata(BaseModel):
    schema_version: int = Field(
        default=RUN_METADATA_SCHEMA_VERSION,
        description="Version of the on-disk run metadata format.",
    )

    run_id: str = Field(
        ...,
        description="Unique identifier for this run.",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Time at which the run was first created.",
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Time at which the run record was last persisted.",
    )

    owner_id: str | None = Field(
        default=None,
        description=(
            "ID of the authenticated user that created this run via the API, "
            "or None for CLI-created runs (which have no user concept)."
        ),
    )

    project_id: str | None = Field(
        default=None,
        description=(
            "ID of the Project this run belongs to. Best-effort/cache-only: "
            "legacy on-disk metadata.json files predating the Project entity "
            "deserialize with None here even though the DB backfilled a "
            "project for them -- the runs table is the source of truth for "
            "any run created before this field existed."
        ),
    )
