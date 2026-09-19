
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.dependencies import get_application, get_current_user
from backend.api.schemas.mcp import (
    MCPExecuteRequest,
    MCPExecuteResponse,
    MCPHealthCheckResponse,
    MCPMetricsListResponse,
    MCPMetricsOut,
    MCPReconnectResponse,
    MCPRefreshResponse,
    MCPServerListResponse,
    MCPServerOut,
    MCPToolListResponse,
    MCPToolOut,
)
from backend.core.app import Application
from backend.db.models.user import User

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


def _to_server_out(info) -> MCPServerOut:
    return MCPServerOut(
        id=info.id,
        display_name=info.display_name,
        description=info.description,
        transport=info.transport,
        is_remote=info.is_remote,
        endpoint=info.endpoint,
        connection_status=info.connection_status.value,
        auth_type=info.auth_type,
        auth_configured=info.auth_configured,
        tool_count=info.tool_count,
        last_health_check=info.last_health_check,
        version=info.version,
        latency_ms=info.latency_ms,
    )


def _to_tool_out(info) -> MCPToolOut:
    return MCPToolOut(
        identity=info.identity,
        server_name=info.server_name,
        tool_name=info.tool_name,
        description=info.description,
        input_schema=info.input_schema,
    )


@router.get("/servers", response_model=MCPServerListResponse)
def list_servers(
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPServerListResponse:
    servers = application.mcp_management_service.list_servers()

    return MCPServerListResponse(servers=[_to_server_out(s) for s in servers])


@router.get("/servers/{server_name}", response_model=MCPServerOut)
def get_server(
    server_name: str,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPServerOut:
    return _to_server_out(application.mcp_management_service.get_server(server_name))


@router.get("/servers/{server_name}/tools", response_model=MCPToolListResponse)
def list_server_tools(
    server_name: str,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPToolListResponse:
    application.mcp_management_service.get_server(server_name)
    tools = application.mcp_management_service.list_tools(server_name=server_name)

    return MCPToolListResponse(tools=[_to_tool_out(t) for t in tools])


@router.get("/tools", response_model=MCPToolListResponse)
def list_tools(
    q: str | None = None,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPToolListResponse:
    tools = application.mcp_management_service.list_tools(query=q)

    return MCPToolListResponse(tools=[_to_tool_out(t) for t in tools])


@router.post("/servers/{server_name}/health-check", response_model=MCPHealthCheckResponse)
async def check_server_health(
    server_name: str,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPHealthCheckResponse:
    application.mcp_management_service.get_server(server_name)
    result = await application.mcp_management_service.check_health(server_name)

    return MCPHealthCheckResponse(
        server_id=server_name,
        status=result.status.value,
        checked_at=result.checked_at,
        latency_ms=result.latency_ms,
        version=result.version,
        error=result.error,
    )


@router.post("/refresh", response_model=MCPRefreshResponse)
async def refresh_registry(
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPRefreshResponse:
    refreshed = await application.mcp_management_service.refresh_registry()

    return MCPRefreshResponse(refreshed_servers=refreshed)


@router.post("/servers/{server_name}/reconnect", response_model=MCPReconnectResponse)
async def reconnect_server(
    server_name: str,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPReconnectResponse:

    application.mcp_management_service.get_server(server_name)
    await application.mcp_client_manager.close(server_name)
    result = await application.mcp_management_service.check_health(server_name)

    return MCPReconnectResponse(
        server_id=server_name,
        status=result.status.value,
        checked_at=result.checked_at,
        latency_ms=result.latency_ms,
        version=result.version,
        error=result.error,
    )


@router.get("/metrics", response_model=MCPMetricsListResponse)
def list_metrics(
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPMetricsListResponse:
    snapshots = application.mcp_metrics.all_snapshots()

    return MCPMetricsListResponse(
        metrics=[
            MCPMetricsOut(
                server_name=s.server_name,
                total_executions=s.total_executions,
                total_failures=s.total_failures,
                active_requests=s.active_requests,
                last_execution_at=s.last_execution_at,
                connected_since=s.connected_since,
            )
            for s in snapshots
        ]
    )


@router.post("/execute", response_model=MCPExecuteResponse)
def execute_tool(
    request: MCPExecuteRequest,
    application: Application = Depends(get_application),
    current_user: User = Depends(get_current_user),
) -> MCPExecuteResponse:

    result = application.mcp_tool_executor.execute(
        agent=None,
        tool_identity=request.tool_identity,
        arguments=request.arguments,
    )

    return MCPExecuteResponse(
        success=result.success,
        data=result.data,
        truncated=result.truncated,
        error=result.error,
    )
