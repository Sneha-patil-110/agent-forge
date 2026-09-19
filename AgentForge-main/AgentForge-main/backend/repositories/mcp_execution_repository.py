from __future__ import annotations

from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.db.models.mcp_execution import MCPExecutionRecord


class MCPExecutionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add(
        self,
        *,
        run_id: str,
        agent: str,
        server_name: str,
        tool_name: str,
        success: bool,
        duration_ms: float | None,
        error_message: str | None,
        occurred_at: datetime,
    ) -> MCPExecutionRecord:
        record = MCPExecutionRecord(
            run_id=run_id,
            agent=agent,
            server_name=server_name,
            tool_name=tool_name,
            success=success,
            duration_ms=duration_ms,
            error_message=error_message,
            occurred_at=occurred_at,
        )
        self.session.add(record)
        self.session.flush()

        return record

    def list_for_run(self, run_id: str) -> list[MCPExecutionRecord]:
        query = (
            select(MCPExecutionRecord)
            .where(MCPExecutionRecord.run_id == run_id)
            .order_by(MCPExecutionRecord.id.asc())
        )

        return list(self.session.execute(query).scalars())

    def per_server_stats(self) -> list[dict]:
        success = func.sum(case((MCPExecutionRecord.success.is_(True), 1), else_=0))
        failure = func.sum(case((MCPExecutionRecord.success.is_(False), 1), else_=0))

        query = select(
            MCPExecutionRecord.server_name,
            func.count().label("total"),
            success.label("success_count"),
            failure.label("failure_count"),
            func.avg(MCPExecutionRecord.duration_ms).label("avg_duration_ms"),
        ).group_by(MCPExecutionRecord.server_name)

        rows = self.session.execute(query).all()

        return [
            {
                "server_name": row.server_name,
                "total": row.total,
                "success_count": int(row.success_count or 0),
                "failure_count": int(row.failure_count or 0),
                "avg_duration_ms": float(row.avg_duration_ms) if row.avg_duration_ms is not None else None,
            }
            for row in rows
        ]

    def most_used_servers(self, *, limit: int = 5) -> list[tuple[str, int]]:
        query = (
            select(MCPExecutionRecord.server_name, func.count().label("total"))
            .group_by(MCPExecutionRecord.server_name)
            .order_by(func.count().desc())
            .limit(limit)
        )

        return [(row.server_name, row.total) for row in self.session.execute(query).all()]
