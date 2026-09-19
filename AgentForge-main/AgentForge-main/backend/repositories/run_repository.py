from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from backend.db.models.project import ProjectRecord
from backend.db.models.run import RunRecord
from backend.repositories.status_filters import resolve_status_filter


class RunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        run_id: str,
        user_id: uuid.UUID | None,
        status: str,
        current_step: str | None,
        current_agent: str | None,
        error_message: str | None,
        test_retry_count: int,
        review_retry_count: int,
        created_at: datetime,
        updated_at: datetime,
        started_at: datetime | None,
        completed_at: datetime | None,
        project_id: str | None = None,
        request_text: str | None = None,
    ) -> RunRecord:
        record = self.session.get(RunRecord, run_id)

        if record is None:
            record = RunRecord(run_id=run_id, created_at=created_at)
            self.session.add(record)

        record.user_id = user_id
        record.status = status
        record.current_step = current_step
        record.current_agent = current_agent
        record.error_message = error_message
        record.test_retry_count = test_retry_count
        record.review_retry_count = review_retry_count
        record.updated_at = updated_at
        record.started_at = started_at
        record.completed_at = completed_at

        if project_id is not None:
            record.project_id = project_id

        if request_text is not None:
            record.request_text = request_text

        self.session.flush()

        return record

    def get(self, run_id: str) -> RunRecord | None:
        return self.session.get(RunRecord, run_id)

    def upsert_checkpoint_blob(
        self, *, run_id: str, checkpoint_blob: bytes, created_at: datetime, updated_at: datetime
    ) -> RunRecord:
        record = self.session.get(RunRecord, run_id)

        if record is None:
            record = RunRecord(run_id=run_id, created_at=created_at)
            self.session.add(record)

        record.checkpoint_blob = checkpoint_blob
        record.updated_at = updated_at
        self.session.flush()

        return record

    def upsert_blob(
        self,
        *,
        run_id: str,
        state_json: str | None,
        metadata_json: str | None,
        created_at: datetime,
        updated_at: datetime,
    ) -> RunRecord:
        record = self.session.get(RunRecord, run_id)

        if record is None:
            record = RunRecord(run_id=run_id, created_at=created_at)
            self.session.add(record)

        if state_json is not None:
            record.state_json = state_json

        if metadata_json is not None:
            record.run_metadata_json = metadata_json

        record.updated_at = updated_at
        self.session.flush()

        return record

    def list(
        self,
        *,
        user_id: uuid.UUID | None = None,
        status: list[str] | None = None,
        q: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        sort: str = "recently_updated",
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunRecord]:
        query = self._filtered_query(
            user_id=user_id, status=status, q=q, date_from=date_from, date_to=date_to
        )
        query = query.order_by(*self._sort_clauses(sort)).limit(limit).offset(offset)

        return list(self.session.execute(query).scalars())

    def count(
        self,
        *,
        user_id: uuid.UUID | None = None,
        status: list[str] | None = None,
        q: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        query = self._filtered_query(
            user_id=user_id, status=status, q=q, date_from=date_from, date_to=date_to
        )
        count_query = select(func.count()).select_from(query.subquery())

        return int(self.session.execute(count_query).scalar_one())

    def _filtered_query(
        self,
        *,
        user_id: uuid.UUID | None,
        status: list[str] | None,
        q: str | None,
        date_from: datetime | None,
        date_to: datetime | None,
    ):
        query = select(RunRecord)

        if user_id is not None:
            query = query.where(RunRecord.user_id == user_id)

        resolved_status = resolve_status_filter(status)

        if resolved_status is not None:
            query = query.where(RunRecord.status.in_(resolved_status))

        if q:
            like = f"%{q}%"
            query = query.outerjoin(ProjectRecord, RunRecord.project_id == ProjectRecord.id).where(
                or_(
                    RunRecord.run_id.ilike(like),
                    RunRecord.current_agent.ilike(like),
                    RunRecord.request_text.ilike(like),
                    ProjectRecord.name.ilike(like),
                )
            )

        if date_from is not None:
            query = query.where(RunRecord.created_at >= date_from)

        if date_to is not None:
            query = query.where(RunRecord.created_at <= date_to)

        return query

    @staticmethod
    def _sort_clauses(sort: str):
        if sort == "newest":
            return (RunRecord.created_at.desc(),)
        if sort == "oldest":
            return (RunRecord.created_at.asc(),)
        if sort == "duration":
            duration = RunRecord.completed_at - RunRecord.started_at
            return (duration.desc().nulls_last(),)
        if sort == "status":
            priority = case(
                (RunRecord.status == "running", 0),
                (RunRecord.status == "waiting_for_user", 1),
                (RunRecord.status == "failed", 2),
                (RunRecord.status == "initialized", 3),
                else_=4,
            )
            return (priority, RunRecord.updated_at.desc())

        return (RunRecord.updated_at.desc(),)
