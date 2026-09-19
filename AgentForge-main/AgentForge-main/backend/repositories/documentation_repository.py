from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.documentation import DocumentationRecord


class DocumentationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        run_id: str,
        path: str,
        title: str,
        description: str | None,
        generating_agent: str,
        status: str,
    ) -> DocumentationRecord:
        record = self.session.get(DocumentationRecord, (run_id, path))
        now = datetime.now(UTC)

        if record is None:
            record = DocumentationRecord(run_id=run_id, path=path, created_at=now)
            self.session.add(record)

        record.title = title
        record.description = description
        record.generating_agent = generating_agent
        record.status = status
        record.updated_at = now

        self.session.flush()

        return record

    def get(self, run_id: str, path: str) -> DocumentationRecord | None:
        return self.session.get(DocumentationRecord, (run_id, path))

    def delete(self, run_id: str, path: str) -> None:
        record = self.get(run_id, path)

        if record is not None:
            self.session.delete(record)
            self.session.flush()

    def rename(self, run_id: str, old_path: str, new_path: str) -> None:
        record = self.get(run_id, old_path)

        if record is not None:
            record.path = new_path
            self.session.flush()

    def list_for_run(self, run_id: str) -> list[DocumentationRecord]:
        query = (
            select(DocumentationRecord)
            .where(DocumentationRecord.run_id == run_id)
            .order_by(DocumentationRecord.path.asc())
        )

        return list(self.session.execute(query).scalars())
