from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.file_version import FileVersionRecord


class FileVersionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        run_id: str,
        path: str,
        content: str,
        source: str,
        edited_by: str | None,
        created_at: datetime,
    ) -> FileVersionRecord:
        record = FileVersionRecord(
            run_id=run_id,
            path=path,
            content=content,
            source=source,
            edited_by=edited_by,
            created_at=created_at,
        )
        self.session.add(record)
        self.session.flush()

        return record

    def list_for_file(self, run_id: str, path: str) -> list[FileVersionRecord]:
        query = (
            select(FileVersionRecord)
            .where(FileVersionRecord.run_id == run_id, FileVersionRecord.path == path)
            .order_by(FileVersionRecord.id.asc())
        )

        return list(self.session.execute(query).scalars())

    def list_for_run(self, run_id: str) -> list[FileVersionRecord]:
        query = (
            select(FileVersionRecord)
            .where(FileVersionRecord.run_id == run_id)
            .order_by(FileVersionRecord.id.asc())
        )

        return list(self.session.execute(query).scalars())

    def get(self, version_id: int) -> FileVersionRecord | None:
        return self.session.get(FileVersionRecord, version_id)
