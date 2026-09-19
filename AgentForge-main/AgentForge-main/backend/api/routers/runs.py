
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.dependencies import (
    enforce_run_creation_rate_limit,
    enforce_run_resume_rate_limit,
    get_application,
    get_current_user,
    get_db_session,
    get_executor,
    get_owned_run,
)
from backend.api.schemas.recovery import (
    CheckpointListOut,
    CheckpointOut,
    FailureDetailOut,
    MCPCallOut,
    RecoveryRecommendationOut,
    RestartFromCheckpointRequest,
    RunLogsOut,
    TimelineEntryOut,
    TimelineOut,
)
from backend.api.schemas.runs import (
    CreateRunRequest,
    RunAccepted,
    RunDetail,
    RunList,
    RunSummary,
    ReviewIssueSummary,
    TestFailureSummary,
)
from backend.core.app import Application
from backend.core.exceptions import RunAlreadyResumingError
from backend.core.failure_classification import RecoveryReason, failure_signature
from backend.core.logging import LOG_DIR
from backend.db.models.user import User
from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.agent_invocation_repository import AgentInvocationRepository
from backend.repositories.mcp_execution_repository import MCPExecutionRepository
from backend.repositories.run_repository import RunRepository
from backend.services.recovery_recommendation import recommend_action
from backend.state.execution_state import WorkflowStatus
from backend.state.run_metadata import RunMetadata

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])

_START_TIMEOUT_SECONDS = 10.0

_start_lock = threading.Lock()


def _to_summary(record) -> RunSummary:
    return RunSummary(
        run_id=record.run_id,
        project_id=record.project_id,
        status=record.status,
        current_step=record.current_step,
        current_agent=record.current_agent,
        error_message=record.error_message,
        test_retry_count=record.test_retry_count,
        review_retry_count=record.review_retry_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


@router.post(
    "",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_creation_rate_limit)],
)
def create_run(
    payload: CreateRunRequest,
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    current_user: User = Depends(get_current_user),
) -> RunAccepted:
    captured: dict[str, str] = {}
    ready = threading.Event()

    def _capture_run_id(event: WorkflowEvent) -> None:
        if event.event_type == EventType.WORKFLOW_STARTED:
            captured["run_id"] = event.run_id
            ready.set()

    def _run_in_background() -> None:
        try:
            application.start_run(payload.request, owner_id=str(current_user.id))
        except Exception:
            logger.exception("Background workflow run failed for request: %s", payload.request)

    with _start_lock:
        application.event_dispatcher.subscribe(_capture_run_id)

        try:
            executor.submit(_run_in_background)

            if not ready.wait(timeout=_START_TIMEOUT_SECONDS):
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Timed out waiting for the run to start.",
                )
        finally:
            application.event_dispatcher.unsubscribe(_capture_run_id)

    return RunAccepted(run_id=captured["run_id"], status=WorkflowStatus.RUNNING.value)


@router.post(
    "/{run_id}/resume",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_resume_rate_limit)],
)
def resume_run(
    run_id: str,
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunAccepted:
    current_state = application.run_service.load_state(metadata.run_id)

    if current_state.execution.workflow_status in (
        WorkflowStatus.COMPLETED,
        WorkflowStatus.COMPLETED_WITH_VERIFICATION_ISSUES,
        WorkflowStatus.FAILED,
    ):
        return RunAccepted(run_id=run_id, status=current_state.execution.workflow_status.value)

    if application.is_resuming(run_id):
        raise RunAlreadyResumingError(f"Run {run_id} is already being resumed.")

    application.mark_resuming(run_id)

    def _resume_in_background() -> None:
        try:
            application.resume_run(run_id)
        except Exception:
            logger.exception("Background resume failed for run %s", run_id)
        finally:
            application.clear_resuming(run_id)

    executor.submit(_resume_in_background)

    return RunAccepted(run_id=run_id, status=WorkflowStatus.RUNNING.value)


@router.post(
    "/{run_id}/retry-agent",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_resume_rate_limit)],
)
def retry_failed_agent(
    run_id: str,
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunAccepted:

    if application.is_resuming(run_id):
        raise RunAlreadyResumingError(f"Run {run_id} is already being resumed.")

    application.mark_resuming(run_id)

    def _retry_in_background() -> None:
        try:
            application.retry_failed_agent(run_id)
        except Exception:
            logger.exception("Background retry-agent failed for run %s", run_id)
        finally:
            application.clear_resuming(run_id)

    executor.submit(_retry_in_background)

    return RunAccepted(run_id=run_id, status=WorkflowStatus.RUNNING.value)


@router.post(
    "/{run_id}/restart-checkpoint",
    response_model=RunAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_resume_rate_limit)],
)
def restart_from_checkpoint(
    run_id: str,
    payload: RestartFromCheckpointRequest,
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunAccepted:
    if application.is_resuming(run_id):
        raise RunAlreadyResumingError(f"Run {run_id} is already being resumed.")

    application.mark_resuming(run_id)

    def _restart_in_background() -> None:
        try:
            application.restart_from_checkpoint(run_id, payload.checkpoint_id)
        except Exception:
            logger.exception("Background restart-from-checkpoint failed for run %s", run_id)
        finally:
            application.clear_resuming(run_id)

    executor.submit(_restart_in_background)

    return RunAccepted(run_id=run_id, status=WorkflowStatus.RUNNING.value)


@router.get("/{run_id}/checkpoints", response_model=CheckpointListOut)
def list_checkpoints(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> CheckpointListOut:
    checkpoints = application.checkpoint_service.list_checkpoints(metadata.run_id)

    return CheckpointListOut(
        run_id=metadata.run_id,
        checkpoints=[
            CheckpointOut(checkpoint_id=c.checkpoint_id, node_name=c.node_name, timestamp=c.timestamp)
            for c in checkpoints
        ],
    )


@router.get("/{run_id}/timeline", response_model=TimelineOut)
def get_run_timeline(
    metadata: RunMetadata = Depends(get_owned_run),
    session: Session = Depends(get_db_session),
) -> TimelineOut:
    rows = AgentInvocationRepository(session).list_for_run(metadata.run_id)
    mcp_rows = MCPExecutionRepository(session).list_for_run(metadata.run_id)

    return TimelineOut(
        run_id=metadata.run_id,
        entries=[
            TimelineEntryOut(
                agent=row.agent,
                attempt_number=row.attempt_number,
                status=row.status,
                duration_ms=row.duration_ms,
                started_at=row.started_at,
                completed_at=row.completed_at,
                provider=row.provider,
                model=row.model,
                failure_category=row.failure_category,
                recovery_reason=row.recovery_reason,
            )
            for row in rows
        ],
        mcp_calls=[
            MCPCallOut(
                agent=row.agent,
                server_name=row.server_name,
                tool_name=row.tool_name,
                success=row.success,
                duration_ms=row.duration_ms,
                occurred_at=row.occurred_at,
            )
            for row in mcp_rows
        ],
    )


@router.get("/{run_id}/failure", response_model=FailureDetailOut)
def get_failure_detail(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
    session: Session = Depends(get_db_session),
) -> FailureDetailOut:
    state = application.run_service.load_state(metadata.run_id)
    is_failed = state.execution.workflow_status == WorkflowStatus.FAILED

    repository = AgentInvocationRepository(session)
    latest_failure = repository.most_recent_failure(metadata.run_id)
    rows = repository.list_for_run(metadata.run_id)

    last_successful_agent = next(
        (row.agent for row in reversed(rows) if row.status == "success"), None
    )

    repeated_failure = False

    if latest_failure is not None:
        same_agent_failures = [
            row for row in rows if row.agent == latest_failure.agent and row.status == "failure"
        ]

        if len(same_agent_failures) >= 2:
            previous_failure = same_agent_failures[-2]
            reason = RecoveryReason(latest_failure.recovery_reason or RecoveryReason.UNKNOWN.value)
            previous_reason = RecoveryReason(
                previous_failure.recovery_reason or RecoveryReason.UNKNOWN.value
            )
            repeated_failure = failure_signature(
                latest_failure.agent, reason, latest_failure.error_message
            ) == failure_signature(
                previous_failure.agent, previous_reason, previous_failure.error_message
            )

    checkpoints = application.checkpoint_service.list_checkpoints(metadata.run_id)
    last_checkpoint = checkpoints[0] if checkpoints else None

    recommendation = None

    if is_failed:
        reason = RecoveryReason(
            (latest_failure.recovery_reason if latest_failure else None) or RecoveryReason.UNKNOWN.value
        )
        rec = recommend_action(reason, repeated_failure=repeated_failure)
        recommendation = RecoveryRecommendationOut(
            mode=rec.mode.value, confidence=rec.confidence, explanation=rec.explanation
        )

    return FailureDetailOut(
        run_id=metadata.run_id,
        is_failed=is_failed,
        failed_agent=state.execution.current_agent.value if state.execution.current_agent else None,
        last_successful_agent=last_successful_agent,
        failed_at=state.execution.completed_at,
        test_retry_count=state.execution.test_retry_count,
        review_retry_count=state.execution.review_retry_count,
        error_message=state.execution.error_message,
        failure_category=latest_failure.failure_category if latest_failure else None,
        recovery_reason=latest_failure.recovery_reason if latest_failure else None,
        provider=latest_failure.provider if latest_failure else None,
        model=latest_failure.model if latest_failure else None,
        duration_ms=latest_failure.duration_ms if latest_failure else None,
        repeated_failure=repeated_failure,
        last_checkpoint_id=last_checkpoint.checkpoint_id if last_checkpoint else None,
        last_checkpoint_timestamp=last_checkpoint.timestamp if last_checkpoint else None,
        recommendation=recommendation,
    )


_MAX_LOG_LINES = 500


@router.get("/{run_id}/logs", response_model=RunLogsOut)
def get_run_logs(
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunLogsOut:

    log_file = LOG_DIR / "app.log"

    if not log_file.exists():
        return RunLogsOut(run_id=metadata.run_id, lines=[], truncated=False)

    marker = f"run={metadata.run_id} "
    matched: list[str] = []

    with log_file.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if marker in line:
                matched.append(line.rstrip("\n"))

    truncated = len(matched) > _MAX_LOG_LINES

    return RunLogsOut(
        run_id=metadata.run_id,
        lines=matched[-_MAX_LOG_LINES:],
        truncated=truncated,
    )


@router.get("", response_model=RunList)
def list_runs(
    status_filter: list[str] | None = Query(None),
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "recently_updated",
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> RunList:
    repository = RunRepository(session)
    records = repository.list(
        user_id=current_user.id,
        status=status_filter,
        q=q,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    total_count = repository.count(
        user_id=current_user.id, status=status_filter, q=q, date_from=date_from, date_to=date_to
    )

    return RunList(
        runs=[_to_summary(record) for record in records],
        total_count=total_count,
        has_more=offset + len(records) < total_count,
    )


@router.get("/{run_id}", response_model=RunDetail)
def get_run(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunDetail:
    state = application.run_service.load_state(metadata.run_id)

    return RunDetail(
        run_id=metadata.run_id,
        project_id=metadata.project_id,
        status=state.execution.workflow_status.value,
        current_step=state.execution.current_step,
        current_agent=state.execution.current_agent.value if state.execution.current_agent else None,
        error_message=state.execution.error_message,
        test_retry_count=state.execution.test_retry_count,
        review_retry_count=state.execution.review_retry_count,
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
        started_at=state.execution.started_at,
        completed_at=state.execution.completed_at,
        project_name=state.project.project_name,
        dependency_retry_count=state.execution.dependency_retry_count,
        testing_result=(
            ("passed" if state.testing.tests_executed else "no_tests_discovered")
            if state.testing.passed
            else state.testing.status.value
        ),
        discovery_status=state.testing.discovery_status.value if state.testing.discovery_status else None,
        tests_discovered=state.testing.tests_discovered,
        tests_executed=state.testing.tests_executed,
        verification_method=state.testing.verification_method,
        review_passed=state.review.passed,
        review_score=state.review.score,
        review_auto_passed=state.review.auto_passed,
        review_auto_pass_reason=state.review.auto_pass_reason,
        review_attempt_number=state.review.attempt_number,
        review_summary=state.review.review_summary,
        review_issues=[
            ReviewIssueSummary(
                title=issue.title,
                description=issue.description,
                severity=issue.severity.value,
                file_path=issue.file_path,
                suggestion=issue.suggestion,
            )
            for issue in state.review.issues
        ],
        files_materialized=len(state.implementation.written_files),
        total_tests=state.testing.total_tests,
        passed_tests=state.testing.passed_tests,
        failed_tests_count=len(state.testing.failed_tests),
        failed_test_names=[
            TestFailureSummary(name=f.name, message=f.message, file_path=f.file_path)
            for f in state.testing.failed_tests
        ],
        failure_classification=state.testing.classification.value if state.testing.classification else None,
        tester_summary=state.tester_analysis.summary,
    )


@router.get("/{run_id}/status", response_model=RunSummary)
def get_run_status(
    application: Application = Depends(get_application),
    metadata: RunMetadata = Depends(get_owned_run),
) -> RunSummary:
    state = application.run_service.load_state(metadata.run_id)

    return RunSummary(
        run_id=metadata.run_id,
        project_id=metadata.project_id,
        status=state.execution.workflow_status.value,
        current_step=state.execution.current_step,
        current_agent=state.execution.current_agent.value if state.execution.current_agent else None,
        error_message=state.execution.error_message,
        test_retry_count=state.execution.test_retry_count,
        review_retry_count=state.execution.review_retry_count,
        created_at=metadata.created_at,
        updated_at=metadata.updated_at,
        started_at=state.execution.started_at,
        completed_at=state.execution.completed_at,
    )
