
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from backend.core.exceptions import AgentForgeException
from backend.state.workflow_state import WorkflowState

if TYPE_CHECKING:
    from backend.mcp.executor import MCPToolExecutor
    from backend.mcp.registry import MCPToolRegistry

logger = logging.getLogger(__name__)

_LIBRARY_ID_PATTERN = re.compile(r"Context7-compatible library ID:\s*(\S+)")

_DOCS_QUERY_TEMPLATE = (
    "Most commonly used APIs, conventions, and current best practices for {technology}."
)


class DocumentationPrefetchService:
    def __init__(
        self,
        *,
        mcp_executor: "MCPToolExecutor | None",
        mcp_registry: "MCPToolRegistry | None",
    ) -> None:
        self.mcp_executor = mcp_executor
        self.mcp_registry = mcp_registry

    def ensure_cached(self, state: WorkflowState) -> None:

        if self.mcp_executor is None or self.mcp_registry is None:
            return

        if not self.mcp_registry.has("context7.resolve-library-id") or not self.mcp_registry.has(
            "context7.query-docs"
        ):
            return

        for technology in state.project.tech_stack:
            if not technology or technology in state.research.documentation:
                continue

            try:
                self._fetch_one(state, technology)
            except AgentForgeException:
                logger.warning(
                    "Failed to prefetch Context7 documentation for '%s'", technology, exc_info=True
                )

    def _fetch_one(self, state: WorkflowState, technology: str) -> None:
        resolved = self.mcp_executor.execute(
            agent=None,
            tool_identity="context7.resolve-library-id",
            arguments={"query": technology, "libraryName": technology},
        )

        library_id = self._extract_library_id(resolved.data)

        if library_id is None:
            logger.info("No Context7 library match for '%s'; skipping prefetch", technology)
            return

        docs = self.mcp_executor.execute(
            agent=None,
            tool_identity="context7.query-docs",
            arguments={
                "libraryId": library_id,
                "query": _DOCS_QUERY_TEMPLATE.format(technology=technology),
            },
        )

        if docs.data:
            state.research.documentation[technology] = docs.data

    @staticmethod
    def _extract_library_id(text: str | None) -> str | None:
        if not text:
            return None

        match = _LIBRARY_ID_PATTERN.search(text)

        return match.group(1) if match else None
