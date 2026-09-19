from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class KnowledgeEntryOut(BaseModel):
    id: str
    run_id: str
    category: str
    title: str
    content: str
    created_by: str
    status: str
    source_id: str | None
    supersedes: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeList(BaseModel):
    entries: list[KnowledgeEntryOut]