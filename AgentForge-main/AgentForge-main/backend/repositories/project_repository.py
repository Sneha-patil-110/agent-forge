from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from backend.db.models.project import ProjectRecord
from backend.db.models.run import RunRecord
from backend.repositories.status_filters import resolve_status_filter


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        id: str,
        user_id: uuid.UUID | None,
        name: str | None,
        initial_prompt: str | None,
    ) -> ProjectRecord:
        now = datetime.now(UTC)
        record = ProjectRecord(
            id=id,
            user_id=user_id,
            name=name,
            initial_prompt=initial_prompt,
            status="initialized",
            run_count=0,
            latest_run_id=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(record)
        self.session.flush()

        return record

    def get(self, project_id: str) -> ProjectRecord | None:
        return self.session.get(ProjectRecord, project_id)

    def get_owned(self, project_id: str, user_id: uuid.UUID) -> ProjectRecord | None:
        record = self.session.get(ProjectRecord, project_id)

        if record is None or record.deleted_at is not None:
            return None

        if record.user_id is None or record.user_id != user_id:
            return None

        return record

    def attach_run(self, project_id: str, run_id: str) -> None:

        record = self.session.get(ProjectRecord, project_id)

        if record is None or record.latest_run_id == run_id:
            return

        record.latest_run_id = run_id
        record.run_count += 1
        record.updated_at = datetime.now(UTC)

        self.session.flush()

    def update_status(self, project_id: str, status: str) -> None:
        record = self.session.get(ProjectRecord, project_id)

        if record is None:
            return

        record.status = status
        record.updated_at = datetime.now(UTC)

        self.session.flush()

    def rename(self, project_id: str, name: str) -> ProjectRecord | None:
        record = self.session.get(ProjectRecord, project_id)

        if record is None:
            return None

        record.name = name
        record.updated_at = datetime.now(UTC)
        self.session.flush()

        return record

    def soft_delete(self, project_id: str) -> None:
        record = self.session.get(ProjectRecord, project_id)

        if record is None:
            return

        record.deleted_at = datetime.now(UTC)
        self.session.flush()

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
    ) -> list[ProjectRecord]:
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
        query = select(ProjectRecord).where(ProjectRecord.deleted_at.is_(None))

        if user_id is not None:
            query = query.where(ProjectRecord.user_id == user_id)

        resolved_status = resolve_status_filter(status)

        if resolved_status is not None:
            query = query.where(ProjectRecord.status.in_(resolved_status))

        if q:
            like = f"%{q}%"
            query = query.where(
                or_(ProjectRecord.name.ilike(like), ProjectRecord.initial_prompt.ilike(like))
            )

        if date_from is not None:
            query = query.where(ProjectRecord.created_at >= date_from)

        if date_to is not None:
            query = query.where(ProjectRecord.created_at <= date_to)

        return query

    @staticmethod
    def _sort_clauses(sort: str):
        if sort == "newest":
            return (ProjectRecord.created_at.desc(),)
        if sort == "oldest":
            return (ProjectRecord.created_at.asc(),)
        if sort == "status":
            priority = case(
                (ProjectRecord.status == "running", 0),
                (ProjectRecord.status == "waiting_for_user", 1),
                (ProjectRecord.status == "failed", 2),
                (ProjectRecord.status == "initialized", 3),
                else_=4,
            )
            return (priority, ProjectRecord.updated_at.desc())

        return (ProjectRecord.updated_at.desc(),)

    def list_for_run_lookup(self, run_id: str) -> ProjectRecord | None:

        run = self.session.get(RunRecord, run_id)

        if run is None or run.project_id is None:
            return None

        return self.session.get(ProjectRecord, run.project_id)
