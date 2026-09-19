from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastmcp.exceptions import FastMCPError
try:
    from mcp.shared.exceptions import McpError
except ImportError:
    # Fallback for newer mcp versions
    try:
        from mcp.exceptions import McpError
    except ImportError:
        # If McpError is not found, create a simple Exception
        class McpError(Exception):
            pass
from pydantic import BaseModel

from backend.core.constants import MAX_MCP_RESULT_CHARS
from backend.core.exceptions import (
    MCPPermissionDeniedError,
    MCPTimeoutError,
    MCPToolExecutionError,
)
from backend.core.run_context import get_current_run_id, set_current_run_id
from backend.core.workspace import REPOSITORY_ROOT
from backend.events.dispatcher import EventDispatcher
from backend.events.event_types import EventType, WorkflowEvent
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.discovery import DiscoveredTool
from backend.mcp.mcp_loop_runner import MCPLoopRunner
from backend.mcp.metrics import MCPMetricsCollector
from backend.mcp.permissions import MCPPermissionPolicy
from backend.mcp.registry import MCPToolRegistry
from backend.services.tracing_service import TracingService
from backend.state.execution_state import AgentType

logger = logging.getLogger(__name__)

_REPO_ROOT_VARIANTS = tuple(
    {str(REPOSITORY_ROOT), str(REPOSITORY_ROOT).replace("\\", "/")}
)


def _redact_local_paths(text: str) -> str:
    if not text:
        return text

    for variant in _REPO_ROOT_VARIANTS:
        text = text.replace(variant, "<agentforge>")

    return text


class MCPToolResult(BaseModel):
    success: bool
    data: str | None = None
    truncated: bool = False
    error: str | None = None
    timing_metadata: dict[str, float] = {}


class MCPToolExecutor:

    def __init__(
        self,
        *,
        client_manager: MCPClientManager,
        registry: MCPToolRegistry,
        permission_policy: MCPPermissionPolicy,
        event_dispatcher: EventDispatcher | None = None,
        tracing_service: TracingService | None = None,
        metrics: MCPMetricsCollector | None = None,
    ) -> None:
        self.client_manager = client_manager
        self.registry = registry
        self.permission_policy = permission_policy
        self.event_dispatcher = event_dispatcher
        self.tracing_service = tracing_service or TracingService.disabled()
        self.metrics = metrics or MCPMetricsCollector()

    def execute(
        self,
        *,
        agent: AgentType | None,
        tool_identity: str,
        arguments: dict[str, Any],
    ) -> MCPToolResult:

        run_id = get_current_run_id()

        tool = self.registry.get(tool_identity)
        agent_label = agent.value if agent is not None else "human"

        tool_requested_at = time.monotonic()
        logger.info(
            "Raw MCP tool request: agent=%s, tool=%s, arguments=%s, run_id=%s",
            agent_label,
            tool_identity,
            arguments,
            run_id,
        )

        with self.tracing_service.trace(
            f"mcp:{tool_identity}",
            run_type="tool",
            tags=[f"agent:{agent_label}", f"mcp_server:{tool.server_name}"],
            metadata={
                "agent": agent_label,
                "mcp_server": tool.server_name,
                "mcp_tool": tool.tool_name,
                "argument_count": len(arguments),
            },
        ) as span:
            started_at = time.perf_counter()
            tool_started_at = time.monotonic()

            if agent is not None and not self.permission_policy.is_authorized(agent, tool_identity):
                raise MCPPermissionDeniedError(
                    f"Agent '{agent.value}' is not authorized to use tool '{tool_identity}'.",
                    details={"agent": agent.value, "tool": tool_identity},
                )

            self._emit(EventType.MCP_TOOL_CALL_STARTED, run_id, agent, tool_identity)
            self.metrics.record_start(tool.server_name)

            try:
                runner = MCPLoopRunner.get_instance()
                result = runner.run_coro(
                    self._call(tool, arguments),
                    timeout=self.client_manager.config_for(tool.server_name).tool_timeout,
                )
            except McpError as error:
                self._fail(run_id, agent, tool, tool_identity, started_at, error)
                if "timed out" in str(error).lower():
                    raise MCPTimeoutError(
                        f"MCP tool '{tool_identity}' timed out: {error}",
                        details={"tool": tool_identity},
                    ) from error
                raise MCPToolExecutionError(
                    f"MCP protocol error calling '{tool_identity}': {error}",
                    details={"tool": tool_identity},
                ) from error
            except FastMCPError as error:
                self._fail(run_id, agent, tool, tool_identity, started_at, error)
                raise MCPToolExecutionError(
                    f"MCP tool '{tool_identity}' failed: {error}",
                    details={"tool": tool_identity},
                ) from error
            except Exception as error:
                self._fail(run_id, agent, tool, tool_identity, started_at, error)
                raise MCPToolExecutionError(
                    f"Unexpected error calling MCP tool '{tool_identity}': {error}",
                    details={"tool": tool_identity},
                ) from error

            tool_finished_at = time.monotonic()
            completed_emitted_at_start = time.monotonic()
            self._emit(EventType.MCP_TOOL_CALL_COMPLETED, run_id, agent, tool_identity)
            metrics_recorded_at_start = time.monotonic()
            self.metrics.record_success(tool.server_name)
            recorded_emitted_at_start = time.monotonic()
            self._emit_recorded(
                run_id, agent, tool, tool_identity, duration_ms=round((time.perf_counter() - started_at) * 1000, 2), success=True
            )
            executor_finished_at = time.monotonic()

            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            post_result_ms = round((executor_finished_at - tool_finished_at) * 1000, 2)

            timing_metadata = {
                "tool_requested_at": tool_requested_at,
                "tool_started_at": tool_started_at,
                "tool_finished_at": tool_finished_at,
                "completed_emitted_ms": round((metrics_recorded_at_start - completed_emitted_at_start) * 1000, 2),
                "metrics_recorded_ms": round((recorded_emitted_at_start - metrics_recorded_at_start) * 1000, 2),
                "recorded_emitted_ms": round((executor_finished_at - recorded_emitted_at_start) * 1000, 2),
                "post_result_processing_ms": post_result_ms,
                "duration_ms": duration_ms,
            }
            result.timing_metadata = timing_metadata

            if post_result_ms > 50.0:
                logger.warning("MCP tool post-result boundary timing delay detected: %s", timing_metadata)

            self.tracing_service.set_outputs(
                span,
                {
                    "success": result.success,
                    "truncated": result.truncated,
                    "result_size": len(result.data) if result.data else 0,
                    "duration_ms": duration_ms,
                    "post_result_processing_ms": post_result_ms,
                },
            )

            return result


    def _fail(
        self,
        run_id: str | None,
        agent: AgentType | None,
        tool: DiscoveredTool,
        tool_identity: str,
        started_at: float,
        error: Exception,
    ) -> None:
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        error_text = _redact_local_paths(str(error))

        self._emit(
            EventType.MCP_TOOL_CALL_FAILED, run_id, agent, tool_identity,
            message=error_text,
        )
        self.metrics.record_failure(tool.server_name)
        self._emit_recorded(
            run_id, agent, tool, tool_identity,
            duration_ms=duration_ms, success=False, error_message=error_text[:500],
        )

    async def _call(self, tool: DiscoveredTool, arguments: dict[str, Any]) -> MCPToolResult:
        config = self.client_manager.config_for(tool.server_name)
        client = await self.client_manager.get_client(tool.server_name)

        raw_result = await client.call_tool(
            tool.tool_name,
            arguments,
            timeout=config.tool_timeout,
        )

        return self._bound_result(raw_result)

    @staticmethod
    def _bound_result(raw_result: Any) -> MCPToolResult:
        data = raw_result.data

        if data is None:
            content_blocks = getattr(raw_result, "content", None) or []
            text = "\n".join(
                block.text for block in content_blocks if getattr(block, "text", None)
            )
        elif isinstance(data, str):
            text = data
        else:
            try:
                text = json.dumps(data, default=str)
            except TypeError:
                text = str(data)

        text = _redact_local_paths(text)

        truncated = len(text) > MAX_MCP_RESULT_CHARS

        if truncated:
            omitted = len(text) - MAX_MCP_RESULT_CHARS
            text = text[:MAX_MCP_RESULT_CHARS] + f"\n... [{omitted} characters truncated]"

        return MCPToolResult(success=True, data=text, truncated=truncated)

    def _emit(
        self,
        event_type: EventType,
        run_id: str | None,
        agent: AgentType | None,
        tool_identity: str,
        *,
        message: str | None = None,
    ) -> None:
        if self.event_dispatcher is None or run_id is None:
            return

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=event_type,
                run_id=run_id,
                agent=agent,
                message=message,
                metadata={"tool": tool_identity},
            )
        )

    def _emit_recorded(
        self,
        run_id: str | None,
        agent: AgentType | None,
        tool: DiscoveredTool,
        tool_identity: str,
        *,
        duration_ms: float,
        success: bool,
        error_message: str | None = None,
    ) -> None:

        if self.event_dispatcher is None or run_id is None:
            return

        self.event_dispatcher.emit(
            WorkflowEvent(
                event_type=EventType.MCP_TOOL_CALL_RECORDED,
                run_id=run_id,
                agent=agent,
                metadata={
                    "server_name": tool.server_name,
                    "tool_name": tool.tool_name,
                    "tool_identity": tool_identity,
                    "duration_ms": duration_ms,
                    "success": success,
                    "error_message": error_message,
                },
            )
        )
