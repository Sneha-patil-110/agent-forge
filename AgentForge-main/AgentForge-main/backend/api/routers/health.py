from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_application
from backend.core.app import Application
from backend.core.constants import AGENTFORGE_VERSION
from backend.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/")
def root() -> dict:
    return {"name": settings.APP_NAME, "version": AGENTFORGE_VERSION}


@router.get("/health")
def health(application: Application = Depends(get_application)) -> dict:
    return {
        "status": "ok",
        "database": "connected" if application.db_session_factory is not None else "unavailable",
    }


@router.get("/version")
def version() -> dict:
    return {"version": AGENTFORGE_VERSION}