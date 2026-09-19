from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.db.models.agent_invocation import AgentInvocationRecord
from backend.db.models.run import RunRecord


class AgentInvocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        run_id: str,
        agent: str,
        attempt_number: int,
        repair_trigger: str | None,
        status: str,
        provider: str | None,
        model: str | None,
        provider_request_id: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
        prompt_characters: int | None,
        response_characters: int | None,
        exception_type: str | None,
        failure_category: str | None,
        recovery_reason: str | None,
        error_message: str | None,
        stacktrace: str | None,
        checkpoint_id: str | None,
        duration_ms: int | None,
        started_at: datetime,
        completed_at: datetime | None,
    ) -> AgentInvocationRecord:
        record = AgentInvocationRecord(
            run_id=run_id,
            agent=agent,
            attempt_number=attempt_number,
            repair_trigger=repair_trigger,
            status=status,
            provider=provider,
            model=model,
            provider_request_id=provider_request_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            prompt_characters=prompt_characters,
            response_characters=response_characters,
            exception_type=exception_type,
            failure_category=failure_category,
            recovery_reason=recovery_reason,
            error_message=error_message,
            stacktrace=stacktrace,
            checkpoint_id=checkpoint_id,
            duration_ms=duration_ms,
            started_at=started_at,
            completed_at=completed_at,
        )
        self.session.add(record)
        self.session.flush()

        return record

    def list_for_run(self, run_id: str) -> list[AgentInvocationRecord]:
        query = (
            select(AgentInvocationRecord)
            .where(AgentInvocationRecord.run_id == run_id)
            .order_by(AgentInvocationRecord.id.asc())
        )

        return list(self.session.execute(query).scalars())

    def most_recent_failure(self, run_id: str) -> AgentInvocationRecord | None:
        query = (
            select(AgentInvocationRecord)
            .where(AgentInvocationRecord.run_id == run_id, AgentInvocationRecord.status == "failure")
            .order_by(AgentInvocationRecord.id.desc())
            .limit(1)
        )

        return self.session.execute(query).scalars().first()

    def recent_failures(self, *, limit: int = 50) -> list[AgentInvocationRecord]:
        query = (
            select(AgentInvocationRecord)
            .where(AgentInvocationRecord.status == "failure")
            .order_by(AgentInvocationRecord.id.desc())
            .limit(limit)
        )

        return list(self.session.execute(query).scalars())

    @staticmethod
    def _scope_to_user(query, user_id: uuid.UUID | None):

        if user_id is None:
            return query

        return query.join(RunRecord, AgentInvocationRecord.run_id == RunRecord.run_id).where(
            RunRecord.user_id == user_id
        )

    def per_agent_stats(self, *, user_id: uuid.UUID | None = None) -> list[dict]:
        success = func.sum(case((AgentInvocationRecord.status == "success", 1), else_=0))
        failure = func.sum(case((AgentInvocationRecord.status == "failure", 1), else_=0))

        query = select(
            AgentInvocationRecord.agent,
            func.count().label("total"),
            success.label("success_count"),
            failure.label("failure_count"),
            func.avg(AgentInvocationRecord.duration_ms).label("avg_duration_ms"),
            func.avg(AgentInvocationRecord.input_tokens).label("avg_input_tokens"),
            func.avg(AgentInvocationRecord.output_tokens).label("avg_output_tokens"),
        ).group_by(AgentInvocationRecord.agent)
        query = self._scope_to_user(query, user_id)

        rows = self.session.execute(query).all()

        return [
            {
                "agent": row.agent,
                "total": row.total,
                "success_count": int(row.success_count or 0),
                "failure_count": int(row.failure_count or 0),
                "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms is not None else None,
                "avg_input_tokens": float(row.avg_input_tokens) if row.avg_input_tokens is not None else None,
                "avg_output_tokens": float(row.avg_output_tokens) if row.avg_output_tokens is not None else None,
            }
            for row in rows
        ]

    def failure_category_breakdown(self, *, user_id: uuid.UUID | None = None) -> dict[str, int]:
        query = (
            select(AgentInvocationRecord.failure_category, func.count())
            .where(AgentInvocationRecord.status == "failure")
            .group_by(AgentInvocationRecord.failure_category)
        )
        query = self._scope_to_user(query, user_id)

        return {category or "unknown": count for category, count in self.session.execute(query).all()}

    def recovery_reason_breakdown(
        self, *, agent: str | None = None, user_id: uuid.UUID | None = None
    ) -> dict[str, int]:
        query = select(AgentInvocationRecord.recovery_reason, func.count()).where(
            AgentInvocationRecord.status == "failure"
        )

        if agent is not None:
            query = query.where(AgentInvocationRecord.agent == agent)

        query = query.group_by(AgentInvocationRecord.recovery_reason)
        query = self._scope_to_user(query, user_id)

        return {reason or "unknown": count for reason, count in self.session.execute(query).all()}

    def provider_breakdown(self, *, user_id: uuid.UUID | None = None) -> dict[str, int]:
        query = select(AgentInvocationRecord.provider, func.count()).group_by(AgentInvocationRecord.provider)
        query = self._scope_to_user(query, user_id)

        return {provider or "unknown": count for provider, count in self.session.execute(query).all()}

    def recent_failures_for_agent(
        self, agent: str, *, user_id: uuid.UUID | None = None, limit: int = 20
    ) -> list[AgentInvocationRecord]:
        query = (
            select(AgentInvocationRecord)
            .where(AgentInvocationRecord.agent == agent, AgentInvocationRecord.status == "failure")
            .order_by(AgentInvocationRecord.id.desc())
            .limit(limit)
        )
        query = self._scope_to_user(query, user_id)

        return list(self.session.execute(query).scalars())

    def recovery_mode_success_rates(self) -> dict[str, float]:
        return {}
