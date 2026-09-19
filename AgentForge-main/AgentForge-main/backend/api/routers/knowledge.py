from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db_session, get_owned_run
from backend.api.schemas.knowledge import KnowledgeEntryOut, KnowledgeList
from backend.repositories.knowledge_repository import KnowledgeRepository
from backend.state.run_metadata import RunMetadata

router = APIRouter(prefix="/api/v1/runs", tags=["knowledge"])


@router.get("/{run_id}/knowledge", response_model=KnowledgeList)
def list_knowledge(
    category: str | None = None,
    status_filter: str | None = None,
    metadata: RunMetadata = Depends(get_owned_run),
    session: Session = Depends(get_db_session),
) -> KnowledgeList:
    records = KnowledgeRepository(session).list_for_run(
        metadata.run_id, category=category, status=status_filter
    )

    return KnowledgeList(
        entries=[
            KnowledgeEntryOut(
                id=record.id,
                run_id=record.run_id,
                category=record.category,
                title=record.title,
                content=record.content,
                created_by=record.created_by,
                status=record.status,
                source_id=record.source_id,
                supersedes=record.supersedes,
                created_at=record.created_at,
                updated_at=record.updated_at,
            )
            for record in records
        ]
    )
