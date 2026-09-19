
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.api.dependencies import get_current_user, get_db_session
from backend.api.schemas.reliability import (
    AgentDetailOut,
    AgentFailureOut,
    AgentStatsOut,
    ReliabilitySummaryOut,
)
from backend.db.models.user import User
from backend.repositories.agent_invocation_repository import AgentInvocationRepository
from backend.state.execution_state import AgentType

router = APIRouter(prefix="/api/v1/reliability", tags=["reliability"])


def _to_stats_out(row: dict) -> AgentStatsOut:
    total = row["total"]
    success_rate = (row["success_count"] / total) if total else 0.0

    return AgentStatsOut(
        agent=row["agent"],
        total=total,
        success_count=row["success_count"],
        failure_count=row["failure_count"],
        success_rate=round(success_rate, 4),
        avg_duration_ms=row["avg_duration_ms"],
        avg_input_tokens=row["avg_input_tokens"],
        avg_output_tokens=row["avg_output_tokens"],
    )


@router.get("/summary", response_model=ReliabilitySummaryOut)
def get_reliability_summary(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ReliabilitySummaryOut:
    repository = AgentInvocationRepository(session)

    per_agent_rows = repository.per_agent_stats(user_id=current_user.id)
    per_agent = [_to_stats_out(row) for row in per_agent_rows]

    overall_total = sum(row["total"] for row in per_agent_rows)
    overall_success = sum(row["success_count"] for row in per_agent_rows)
    overall_success_rate = (overall_success / overall_total) if overall_total else 0.0

    return ReliabilitySummaryOut(
        overall_total=overall_total,
        overall_success_count=overall_success,
        overall_success_rate=round(overall_success_rate, 4),
        per_agent=per_agent,
        failure_category_breakdown=repository.failure_category_breakdown(user_id=current_user.id),
        recovery_reason_breakdown=repository.recovery_reason_breakdown(user_id=current_user.id),
        provider_breakdown=repository.provider_breakdown(user_id=current_user.id),
    )


@router.get("/agents/{agent}", response_model=AgentDetailOut)
def get_agent_reliability_detail(
    agent: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> AgentDetailOut:
    try:
        AgentType(agent)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown agent: {agent}"
        ) from error

    repository = AgentInvocationRepository(session)

    stats_row = next(
        (row for row in repository.per_agent_stats(user_id=current_user.id) if row["agent"] == agent),
        None,
    )
    recent_failures = repository.recent_failures_for_agent(agent, user_id=current_user.id)

    return AgentDetailOut(
        agent=agent,
        stats=_to_stats_out(stats_row) if stats_row is not None else None,
        recovery_reason_breakdown=repository.recovery_reason_breakdown(
            agent=agent, user_id=current_user.id
        ),
        recent_failures=[
            AgentFailureOut(
                run_id=row.run_id,
                attempt_number=row.attempt_number,
                status=row.status,
                exception_type=row.exception_type,
                failure_category=row.failure_category,
                recovery_reason=row.recovery_reason,
                error_message=row.error_message,
                provider=row.provider,
                model=row.model,
                duration_ms=row.duration_ms,
            )
            for row in recent_failures
        ],
    )
