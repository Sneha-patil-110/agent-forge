from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MCPServerOut(BaseModel):
    id: str
    display_name: str
    description: str | None
    transport: str
    is_remote: bool
    endpoint: str
    connection_status: str
    auth_type: str
    auth_configured: bool
    tool_count: int
    last_health_check: datetime | None
    version: str | None
    latency_ms: float | None


class MCPServerListResponse(BaseModel):
    servers: list[MCPServerOut]


class MCPToolOut(BaseModel):
    identity: str
    server_name: str
    tool_name: str
    description: str
    input_schema: dict


class MCPToolListResponse(BaseModel):
    tools: list[MCPToolOut]


class MCPHealthCheckResponse(BaseModel):
    server_id: str
    status: str
    checked_at: datetime
    latency_ms: float | None
    version: str | None
    error: str | None


class MCPRefreshResponse(BaseModel):
    refreshed_servers: list[str]


class MCPReconnectResponse(BaseModel):
    server_id: str
    status: str
    checked_at: datetime
    latency_ms: float | None
    version: str | None
    error: str | None


class MCPExecuteRequest(BaseModel):
    tool_identity: str = Field(..., min_length=1, description="'<server>.<tool>'")
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPExecuteResponse(BaseModel):
    success: bool
    data: str | None
    truncated: bool
    error: str | None


class MCPMetricsOut(BaseModel):
    server_name: str
    total_executions: int
    total_failures: int
    active_requests: int
    last_execution_at: datetime | None
    connected_since: datetime | None


class MCPMetricsListResponse(BaseModel):
    metrics: list[MCPMetricsOut]
