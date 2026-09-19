from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    request: str = Field(..., min_length=1, description="Natural language description of the software to build.")


class ContinueProjectRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Follow-up request continuing this project.")


class RenameProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class ProjectAccepted(BaseModel):
    project_id: str
    run_id: str
    status: str


class ProjectSummaryOut(BaseModel):
    id: str
    name: str | None
    status: str
    run_count: int
    latest_run_id: str | None
    created_at: datetime
    updated_at: datetime


class ProjectDetailOut(ProjectSummaryOut):
    initial_prompt: str | None


class ProjectListOut(BaseModel):
    projects: list[ProjectSummaryOut]
    total_count: int
    has_more: bool


class ConversationMessageOut(BaseModel):
    role: str
    content: str


class ConversationOut(BaseModel):
    project_id: str
    messages: list[ConversationMessageOut]
