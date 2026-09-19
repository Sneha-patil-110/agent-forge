from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class RepositorySnapshot(BaseModel):

    project_root: str = Field(
        ...,
        description="Resolved absolute path to the project root directory.",
    )
    file_tree: list[str] = Field(
        default_factory=list,
        description="Sorted list of relative file paths present on disk.",
    )
    top_level_directories: list[str] = Field(
        default_factory=list,
        description="Top-level subdirectories under project root.",
    )
    project_type: str = Field(
        default="unknown",
        description="Project language or framework type (e.g., python, fastapi, node).",
    )
    entrypoints: list[str] = Field(
        default_factory=list,
        description="Known entrypoint file paths present in the repository.",
    )
    test_configuration: str | dict[str, Any] | None = Field(
        default=None,
        description="Test framework configuration details.",
    )
    known_test_directories: list[str] = Field(
        default_factory=list,
        description="Relative paths to directories containing test modules.",
    )
    content_hash: str | None = Field(
        default=None,
        description=(
            "Deterministic SHA-256 over every file's path and content at "
            "snapshot time. Two snapshots with the same hash are guaranteed "
            "to have byte-identical repository content, regardless of when "
            "they were taken -- used to detect stale state across a repair "
            "cycle (e.g. Tester analyzed one version of the repository, but "
            "a differently-hashed one exists by the time repair happens)."
        ),
    )
