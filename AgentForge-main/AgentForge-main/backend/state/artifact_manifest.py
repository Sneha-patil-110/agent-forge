from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ArtifactFile(BaseModel):
    path: str = Field(
        ...,
        description="Relative path of the artifact file from project root.",
    )
    content: str = Field(
        ...,
        description="Complete file content.",
    )
    language: str = Field(
        default="plaintext",
        description="Programming language or format of the file.",
    )
    description: str | None = Field(
        default=None,
        description="Brief description of the artifact.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata associated with the artifact.",
    )


class ArtifactManifest(BaseModel):
    files: list[ArtifactFile] = Field(
        default_factory=list,
        description="Canonical collection of artifact files for the project.",
    )

    def get_file(self, path: str) -> ArtifactFile | None:
        normalized = path.replace("\\", "/")
        for file in self.files:
            if file.path.replace("\\", "/") == normalized:
                return file
        return None
