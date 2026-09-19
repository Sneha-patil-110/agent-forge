from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.event import WorkflowEventRecord


class EventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        run_id: str,
        event_type: str,
        agent: str | None,
        message: str | None,
        event_metadata: dict,
        timestamp: datetime,
    ) -> WorkflowEventRecord:
        record = WorkflowEventRecord(
            run_id=run_id,
            event_type=event_type,
            agent=agent,
            message=message,
            event_metadata=event_metadata,
            timestamp=timestamp,
        )
        self.session.add(record)
        self.session.flush()

        return record

    def list_for_run(
        self,
        run_id: str,
        *,
        after_id: int | None = None,
        limit: int = 500,
    ) -> list[WorkflowEventRecord]:
        query = (
            select(WorkflowEventRecord)
            .where(WorkflowEventRecord.run_id == run_id)
            .order_by(WorkflowEventRecord.id.asc())
            .limit(limit)
        )

        if after_id is not None:
            query = query.where(WorkflowEventRecord.id > after_id)

        return list(self.session.execute(query).scalars())