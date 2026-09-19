from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RepoFileNodeOut(BaseModel):
    type: str
    name: str
    path: str
    size_bytes: int | None = None
    children: list["RepoFileNodeOut"] = []


class RepoTreeResponse(BaseModel):
    run_id: str
    tree: list[RepoFileNodeOut]


class CreateFileRequest(BaseModel):
    path: str
    content: str = ""


class UpdateFileRequest(BaseModel):
    content: str
    expected_version: str | None = None


class CreateFolderRequest(BaseModel):
    path: str


class RenameRequest(BaseModel):
    new_name: str


class MoveRequest(BaseModel):
    destination: str


class DuplicateRequest(BaseModel):
    destination: str


class FileWriteResponse(BaseModel):
    path: str
    version: str


class FileReadResponse(BaseModel):
    path: str
    content: str
    version: str


class PathResponse(BaseModel):
    path: str


class SearchResultOut(BaseModel):
    path: str
    line: int | None
    snippet: str | None


class SearchResponse(BaseModel):
    matches: list[SearchResultOut]


class FileMetadataOut(BaseModel):
    path: str
    size_bytes: int
    language: str
    last_modified: datetime
    generated_by_ai: bool
    last_edited_by: str | None
    agent: str | None


class FileVersionOut(BaseModel):
    id: int
    source: str
    edited_by: str | None
    created_at: datetime


class FileVersionListResponse(BaseModel):
    path: str
    versions: list[FileVersionOut]


class DiffResponse(BaseModel):
    path: str
    from_version: int | str
    to_version: int | str
    from_content: str
    to_content: str


class DocumentationFileOut(BaseModel):
    title: str
    path: str
    content: str
    description: str | None
    generating_agent: str | None = None
    status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentationListResponse(BaseModel):
    documentation_summary: str | None
    files: list[DocumentationFileOut]
