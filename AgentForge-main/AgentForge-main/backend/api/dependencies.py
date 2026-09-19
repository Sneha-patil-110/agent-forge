from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Iterator

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.core.app import Application
from backend.core.config import settings
from backend.core.exceptions import AgentForgeException, RateLimitError
from backend.db.models.project import ProjectRecord
from backend.db.models.user import User
from backend.repositories.project_repository import ProjectRepository
from backend.repositories.user_repository import UserRepository
from backend.state.run_metadata import RunMetadata

_bearer_scheme = HTTPBearer(auto_error=False)


def get_application(request: Request) -> Application:
    return request.app.state.application


def get_executor(request: Request) -> ThreadPoolExecutor:
    return request.app.state.executor


def get_db_session(application: Application = Depends(get_application)) -> Iterator[Session]:
    if application.db_session_factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured or unreachable.",
        )

    session = application.db_session_factory()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _resolve_user(token: str, application: Application, session: Session) -> User:
    try:
        payload = application.auth_service.decode_access_token(token)
    except AgentForgeException as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject.") from error

    user = UserRepository(session).get_by_id(user_id)

    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive.")

    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    application: Application = Depends(get_application),
    session: Session = Depends(get_db_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    return _resolve_user(credentials.credentials, application, session)


def get_current_user_for_sse(
    request: Request,
    token: str | None = None,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    application: Application = Depends(get_application),
    session: Session = Depends(get_db_session),
) -> User:
    if credentials is not None:
        return _resolve_user(credentials.credentials, application, session)

    query_token = token or request.query_params.get("token")

    if query_token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    return _resolve_user(query_token, application, session)


def get_owned_run(
    run_id: str,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> RunMetadata:

    metadata = application.run_service.load_metadata(run_id)

    if metadata.owner_id is None or metadata.owner_id != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")

    return metadata


def get_owned_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> ProjectRecord:

    record = ProjectRepository(session).get_owned(project_id, current_user.id)

    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project not found: {project_id}")

    return record


def enforce_run_creation_rate_limit(
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> None:
    allowed = application.rate_limiter.check(
        f"run-creation:{current_user.id}",
        limit=settings.RATE_LIMIT_RUN_CREATION_PER_MINUTE,
    )

    if not allowed:
        raise RateLimitError("Too many runs started recently. Try again in a minute.")


def enforce_run_resume_rate_limit(
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> None:
    allowed = application.rate_limiter.check(
        f"run-resume:{current_user.id}",
        limit=settings.RATE_LIMIT_RUN_RESUME_PER_MINUTE,
    )

    if not allowed:
        raise RateLimitError("Too many resume requests recently. Try again in a minute.")