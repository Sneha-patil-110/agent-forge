
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from langsmith import Client
from langsmith.run_helpers import trace as ls_trace
from langsmith.run_helpers import tracing_context as ls_tracing_context
from langsmith.run_trees import RunTree

from backend.core.config import settings

logger = logging.getLogger(__name__)


class TracingService:
    def __init__(self, *, _disabled: bool = False) -> None:
        self.enabled = False
        self._client: Client | None = None

        if _disabled or not settings.LANGSMITH_TRACING:
            return

        if not settings.LANGSMITH_API_KEY:
            logger.warning(
                "LANGSMITH_TRACING is enabled but LANGSMITH_API_KEY is not "
                "set; LangSmith tracing will be disabled."
            )
            return

        try:
            self._client = Client(
                api_url=settings.LANGSMITH_ENDPOINT,
                api_key=settings.LANGSMITH_API_KEY,
                tracing_error_callback=self._on_tracing_error,
            )
        except Exception:
            logger.exception(
                "Failed to initialize the LangSmith client; tracing disabled"
            )
            self._client = None
            return

        self.enabled = True
        logger.info(
            "LangSmith tracing enabled (project=%s)", settings.LANGSMITH_PROJECT
        )

    @classmethod
    def disabled(cls) -> "TracingService":

        return cls(_disabled=True)

    @staticmethod
    def _on_tracing_error(error: BaseException) -> None:
        logger.warning("LangSmith tracing error (non-fatal): %s", error)

    @contextmanager
    def trace(
        self,
        name: str,
        *,
        run_type: str = "chain",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> Iterator[RunTree | None]:

        if not self.enabled:
            yield None
            return

        from backend.mcp.executor import get_current_run_id

        try:
            context_cm = ls_tracing_context(
                enabled=True,
                client=self._client,
                project_name=settings.LANGSMITH_PROJECT,
            )
            context_cm.__enter__()
        except Exception:
            logger.warning(
                "Failed to establish a LangSmith tracing context for '%s'; "
                "continuing untraced",
                name,
                exc_info=True,
            )
            yield None
            return

        try:
            span = ls_trace(
                name,
                run_type=run_type,
                project_name=settings.LANGSMITH_PROJECT,
                client=self._client,
                tags=tags,
                metadata={**(metadata or {}), "run_id": get_current_run_id()},
                inputs=inputs,
            )
            run = span.__enter__()
        except Exception:
            logger.warning(
                "Failed to start LangSmith trace '%s'; continuing untraced",
                name,
                exc_info=True,
            )
            context_cm.__exit__(None, None, None)
            yield None
            return

        try:
            yield run
        except BaseException as error:
            try:
                span.__exit__(type(error), error, error.__traceback__)
            except Exception:
                logger.warning(
                    "Failed to record LangSmith trace failure for '%s'",
                    name,
                    exc_info=True,
                )
            raise
        else:
            try:
                span.__exit__(None, None, None)
            except Exception:
                logger.warning(
                    "Failed to finalize LangSmith trace '%s'", name, exc_info=True
                )
        finally:
            try:
                context_cm.__exit__(None, None, None)
            except Exception:
                logger.warning(
                    "Failed to tear down LangSmith tracing context for '%s'",
                    name,
                    exc_info=True,
                )

    @staticmethod
    def set_outputs(
        run: RunTree | None,
        outputs: dict[str, Any],
        *,
        error: str | None = None,
    ) -> None:

        if run is None:
            return

        try:
            run.end(outputs=outputs, error=error)
        except Exception:
            logger.debug("Failed to attach LangSmith run outputs", exc_info=True)

    def shutdown(self) -> None:

        if self._client is None:
            return

        try:
            self._client.close(timeout=5.0)
        except Exception:
            logger.warning(
                "Failed to close the LangSmith client cleanly", exc_info=True
            )
        finally:
            self._client = None
            self.enabled = False