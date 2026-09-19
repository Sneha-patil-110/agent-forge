
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.exceptions import (
    AgentForgeException,
    AgentValidationError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    DatabaseError,
    InvalidProjectIdError,
    InvalidRepositoryPathError,
    InvalidRunIdError,
    KnowledgeEntryNotFoundError,
    MCPPermissionDeniedError,
    MCPServerNotFoundError,
    MCPToolNotFoundError,
    ProjectNotFoundError,
    RateLimitError,
    RepositoryConflictError,
    RepositoryFileNotTextError,
    RepositoryPathAlreadyExistsError,
    RepositoryPathNotFoundError,
    RunAlreadyResumingError,
    RunCorruptedError,
    RunNotFoundError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_STATUS_BY_EXCEPTION: tuple[tuple[type[AgentForgeException], int], ...] = (
    (InvalidRunIdError, status.HTTP_400_BAD_REQUEST),
    (InvalidProjectIdError, status.HTTP_400_BAD_REQUEST),
    (InvalidRepositoryPathError, status.HTTP_400_BAD_REQUEST),
    (RepositoryFileNotTextError, status.HTTP_400_BAD_REQUEST),
    (RunNotFoundError, status.HTTP_404_NOT_FOUND),
    (ProjectNotFoundError, status.HTTP_404_NOT_FOUND),
    (KnowledgeEntryNotFoundError, status.HTTP_404_NOT_FOUND),
    (MCPToolNotFoundError, status.HTTP_404_NOT_FOUND),
    (MCPServerNotFoundError, status.HTTP_404_NOT_FOUND),
    (RepositoryPathNotFoundError, status.HTTP_404_NOT_FOUND),
    (AuthenticationError, status.HTTP_401_UNAUTHORIZED),
    (AuthorizationError, status.HTTP_403_FORBIDDEN),
    (MCPPermissionDeniedError, status.HTTP_403_FORBIDDEN),
    (AgentValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
    (RepositoryPathAlreadyExistsError, status.HTTP_409_CONFLICT),
    (RepositoryConflictError, status.HTTP_409_CONFLICT),
    (RunAlreadyResumingError, status.HTTP_409_CONFLICT),
    (RateLimitError, status.HTTP_429_TOO_MANY_REQUESTS),
    (RunCorruptedError, status.HTTP_500_INTERNAL_SERVER_ERROR),
    (ConfigurationError, status.HTTP_503_SERVICE_UNAVAILABLE),
    (DatabaseError, status.HTTP_503_SERVICE_UNAVAILABLE),
)


def _status_for(error: AgentForgeException) -> int:
    for exception_type, http_status in _STATUS_BY_EXCEPTION:
        if isinstance(error, exception_type):
            return http_status

    return status.HTTP_400_BAD_REQUEST


def _envelope(message: str, *, error_type: str) -> dict:
    return {"error": {"type": error_type, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AgentForgeException)
    async def _agentforge_exception_handler(request: Request, error: AgentForgeException) -> JSONResponse:
        http_status = _status_for(error)

        if http_status >= 500:
            logger.exception("Unhandled AgentForgeException on %s", request.url.path, exc_info=error)

        return JSONResponse(
            status_code=http_status,
            content=_envelope(str(error), error_type=type(error).__name__),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=_envelope(str(error.detail), error_type="HTTPException"),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_envelope("Request validation failed.", error_type="RequestValidationError")
            | {"details": error.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path, exc_info=error)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("An unexpected error occurred.", error_type="InternalError"),
        )