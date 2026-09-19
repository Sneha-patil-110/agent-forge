from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.knowledge import KnowledgeEntryRecord


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        run_id: str,
        entry_id: str,
        category: str,
        title: str,
        content: str,
        created_by: str,
        status: str,
        source_id: str | None,
        supersedes: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> KnowledgeEntryRecord:
        record = self.session.get(KnowledgeEntryRecord, (run_id, entry_id))

        if record is None:
            record = KnowledgeEntryRecord(run_id=run_id, id=entry_id, created_at=created_at)
            self.session.add(record)

        record.category = category
        record.title = title
        record.content = content
        record.created_by = created_by
        record.status = status
        record.source_id = source_id
        record.supersedes = supersedes
        record.updated_at = updated_at

        self.session.flush()

        return record

    def list_for_run(
        self,
        run_id: str,
        *,
        category: str | None = None,
        status: str | None = None,
    ) -> list[KnowledgeEntryRecord]:
        query = select(KnowledgeEntryRecord).where(KnowledgeEntryRecord.run_id == run_id)

        if category is not None:
            query = query.where(KnowledgeEntryRecord.category == category)

        if status is not None:
            query = query.where(KnowledgeEntryRecord.status == status)

        query = query.order_by(KnowledgeEntryRecord.created_at.asc())

        return list(self.session.execute(query).scalars())