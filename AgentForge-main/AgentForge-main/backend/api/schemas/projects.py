from __future__ import annotations

from pydantic import BaseModel


class RunProjectOut(BaseModel):
    run_id: str
    project_name: str | None
    project_description: str | None
    objective: str | None
    status: str
    backend: str | None
    frontend: str | None
    database: str | None
    deployment: str | None
    requirements: list[str]
    tech_stack: list[str]
    output_directory: str | None


class ProjectFileOut(BaseModel):
    path: str
    size_bytes: int


class ProjectFileList(BaseModel):
    run_id: str
    files: list[ProjectFileOut]


class ProjectFileContent(BaseModel):
    path: str
    content: str