
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.api.dependencies import (
    enforce_run_creation_rate_limit,
    get_application,
    get_current_user,
    get_db_session,
    get_executor,
    get_owned_project,
)
from backend.api.schemas.project_workspace import (
    ConversationMessageOut,
    ConversationOut,
    ContinueProjectRequest,
    CreateProjectRequest,
    ProjectAccepted,
    ProjectDetailOut,
    ProjectListOut,
    ProjectSummaryOut,
    RenameProjectRequest,
)
from backend.core.app import Application
from backend.db.models.project import ProjectRecord
from backend.db.models.user import User
from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.project_repository import ProjectRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])

_START_TIMEOUT_SECONDS = 10.0

_start_lock = threading.Lock()


def _start_and_capture(
    application: Application,
    executor: ThreadPoolExecutor,
    start: Callable[[], None],
) -> tuple[str, str]:

    captured: dict[str, str] = {}
    ready = threading.Event()

    def _capture(event: WorkflowEvent) -> None:
        if event.event_type == EventType.WORKFLOW_STARTED:
            captured["run_id"] = event.run_id
            captured["project_id"] = event.metadata.get("project_id", "")
            ready.set()

    def _run_in_background() -> None:
        try:
            start()
        except Exception:
            logger.exception("Background project workflow run failed.")

    with _start_lock:
        application.event_dispatcher.subscribe(_capture)

        try:
            executor.submit(_run_in_background)

            if not ready.wait(timeout=_START_TIMEOUT_SECONDS):
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Timed out waiting for the run to start.",
                )
        finally:
            application.event_dispatcher.unsubscribe(_capture)

    return captured["project_id"], captured["run_id"]


def _to_summary(record: ProjectRecord) -> ProjectSummaryOut:
    return ProjectSummaryOut(
        id=record.id,
        name=record.name,
        status=record.status,
        run_count=record.run_count,
        latest_run_id=record.latest_run_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.post(
    "",
    response_model=ProjectAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_creation_rate_limit)],
)
def create_project(
    payload: CreateProjectRequest,
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    current_user: User = Depends(get_current_user),
) -> ProjectAccepted:
    project_id, run_id = _start_and_capture(
        application,
        executor,
        lambda: application.start_project_run(
            project_id=None, request=payload.request, owner_id=str(current_user.id)
        ),
    )

    return ProjectAccepted(project_id=project_id, run_id=run_id, status="running")


@router.post(
    "/{project_id}/messages",
    response_model=ProjectAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_creation_rate_limit)],
)
def continue_project(
    payload: ContinueProjectRequest,
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    current_user: User = Depends(get_current_user),
    project: ProjectRecord = Depends(get_owned_project),
) -> ProjectAccepted:
    if project.latest_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project's initial run hasn't started yet. Try again shortly.",
        )

    resolved_project_id, run_id = _start_and_capture(
        application,
        executor,
        lambda: application.start_project_run(
            project_id=project.id,
            request=payload.message,
            owner_id=str(current_user.id),
            latest_run_id=project.latest_run_id,
        ),
    )

    return ProjectAccepted(project_id=resolved_project_id, run_id=run_id, status="running")


@router.post(
    "/{project_id}/restart",
    response_model=ProjectAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_creation_rate_limit)],
)
def restart_project_workflow(
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    current_user: User = Depends(get_current_user),
    project: ProjectRecord = Depends(get_owned_project),
) -> ProjectAccepted:

    if project.latest_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project's initial run hasn't started yet. Try again shortly.",
        )

    resolved_project_id, run_id = _start_and_capture(
        application,
        executor,
        lambda: application.restart_workflow(
            project_id=project.id,
            latest_run_id=project.latest_run_id,
            owner_id=str(current_user.id),
        ),
    )

    return ProjectAccepted(project_id=resolved_project_id, run_id=run_id, status="running")


@router.post(
    "/{project_id}/duplicate",
    response_model=ProjectAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(enforce_run_creation_rate_limit)],
)
def duplicate_project_and_retry(
    application: Application = Depends(get_application),
    executor: ThreadPoolExecutor = Depends(get_executor),
    current_user: User = Depends(get_current_user),
    project: ProjectRecord = Depends(get_owned_project),
) -> ProjectAccepted:

    if project.latest_run_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This project's initial run hasn't started yet. Try again shortly.",
        )

    resolved_project_id, run_id = _start_and_capture(
        application,
        executor,
        lambda: application.duplicate_and_retry(
            latest_run_id=project.latest_run_id, owner_id=str(current_user.id)
        ),
    )

    return ProjectAccepted(project_id=resolved_project_id, run_id=run_id, status="running")


@router.get("", response_model=ProjectListOut)
def list_projects(
    status_filter: list[str] | None = Query(None),
    q: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    sort: str = "recently_updated",
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ProjectListOut:
    repository = ProjectRepository(session)

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

    return ProjectListOut(
        projects=[_to_summary(record) for record in records],
        total_count=total_count,
        has_more=offset + len(records) < total_count,
    )


@router.get("/{project_id}", response_model=ProjectDetailOut)
def get_project_detail(
    project: ProjectRecord = Depends(get_owned_project),
) -> ProjectDetailOut:
    return ProjectDetailOut(
        id=project.id,
        name=project.name,
        status=project.status,
        run_count=project.run_count,
        latest_run_id=project.latest_run_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
        initial_prompt=project.initial_prompt,
    )


@router.patch("/{project_id}", response_model=ProjectDetailOut)
def rename_project(
    payload: RenameProjectRequest,
    project: ProjectRecord = Depends(get_owned_project),
    session: Session = Depends(get_db_session),
) -> ProjectDetailOut:
    updated = ProjectRepository(session).rename(project.id, payload.name)

    return ProjectDetailOut(
        id=updated.id,
        name=updated.name,
        status=updated.status,
        run_count=updated.run_count,
        latest_run_id=updated.latest_run_id,
        created_at=updated.created_at,
        updated_at=updated.updated_at,
        initial_prompt=updated.initial_prompt,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project: ProjectRecord = Depends(get_owned_project),
    session: Session = Depends(get_db_session),
) -> None:
    ProjectRepository(session).soft_delete(project.id)


@router.get("/{project_id}/conversation", response_model=ConversationOut)
def get_project_conversation(
    application: Application = Depends(get_application),
    project: ProjectRecord = Depends(get_owned_project),
) -> ConversationOut:
    if project.latest_run_id is None:
        return ConversationOut(project_id=project.id, messages=[])

    state = application.run_service.load_state(project.latest_run_id)

    messages = [
        ConversationMessageOut(role=message.type, content=message.content)
        for message in state.conversation.messages
        if isinstance(message.content, str)
    ]

    return ConversationOut(project_id=project.id, messages=messages)
