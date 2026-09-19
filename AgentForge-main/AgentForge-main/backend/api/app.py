
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import register_exception_handlers
from backend.api.routers import (
    auth,
    events,
    health,
    knowledge,
    mcp,
    project_workspace,
    projects,
    reliability,
    repository,
    runs,
    workflow_graph,
)
from backend.core.app import Application
from backend.core.config import settings
from backend.core.constants import AGENTFORGE_VERSION, MCP_HEALTH_CHECK_INTERVAL_SECONDS
from backend.core.logging import setup_logging

logger = logging.getLogger(__name__)

_EXECUTOR_MAX_WORKERS = 8


async def _mcp_health_loop(application: Application) -> None:

    while True:
        try:
            await application.mcp_management_service.refresh_registry(skip_known_auth_failures=True)
            await application.mcp_management_service.check_all_health(skip_known_auth_failures=True)
        except Exception:
            logger.warning("MCP background health/refresh pass failed", exc_info=True)

        await asyncio.sleep(MCP_HEALTH_CHECK_INTERVAL_SECONDS)


def create_app(application_factory: Callable[[], Application] = Application) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        setup_logging()

        app.state.application = application_factory()
        app.state.executor = ThreadPoolExecutor(
            max_workers=_EXECUTOR_MAX_WORKERS, thread_name_prefix="agentforge-run"
        )
        app.state.mcp_health_task = asyncio.create_task(
            _mcp_health_loop(app.state.application)
        )

        logger.info("AgentForge API started")

        try:
            yield
        finally:
            app.state.mcp_health_task.cancel()
            app.state.executor.shutdown(wait=False, cancel_futures=False)
            await app.state.application.ashutdown()
            logger.info("AgentForge API stopped")

    app = FastAPI(
        title=settings.APP_NAME,
        version=AGENTFORGE_VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.API_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(runs.router)
    app.include_router(events.router)
    app.include_router(projects.router)
    app.include_router(project_workspace.router)
    app.include_router(knowledge.router)
    app.include_router(auth.router)
    app.include_router(repository.router)
    app.include_router(mcp.router)
    app.include_router(reliability.router)
    app.include_router(workflow_graph.router)

    return app


app = create_app()