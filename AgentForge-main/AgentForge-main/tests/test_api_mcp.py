from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application
from backend.mcp.client_manager import MCPClientManager
from backend.mcp.config import MCPAuthType, MCPServerAuth, MCPServerConfig, MCPTransport
from backend.services.mcp_management_service import MCPManagementService
from backend.services.run_service import RunService
from tests.support.auth import auth_headers, register_and_login
from tests.support.fake_application import FakeApplication

TEST_SERVER_ARGS = ["-m", "tests.support.mcp_test_server"]


def _real_config(**overrides) -> MCPServerConfig:
    defaults = dict(
        name="test",
        display_name="Test Server",
        enabled=True,
        transport=MCPTransport.STDIO,
        command=sys.executable,
        args=TEST_SERVER_ARGS,
    )
    defaults.update(overrides)
    return MCPServerConfig(**defaults)


@pytest.fixture
def client(tmp_path: Path, db_session_factory) -> TestClient:
    fake_app = FakeApplication(
        run_service=RunService(runs_root=tmp_path / "runs"), db_session_factory=db_session_factory
    )
    fake_app.mcp_client_manager = MCPClientManager(
        {
            "test": _real_config(),
            "remote": _real_config(
                name="remote",
                transport=MCPTransport.HTTP,
                command=None,
                args=[],
                url="https://example.com/mcp",
                enabled=False,
                auth=MCPServerAuth(type=MCPAuthType.BEARER, credential_env_var="AGENTFORGE_TEST_REMOTE_TOKEN"),
            ),
        }
    )
    fake_app.mcp_management_service = MCPManagementService(
        client_manager=fake_app.mcp_client_manager,
        tool_registry=fake_app.mcp_tool_registry,
    )

    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    test_client = TestClient(app)
    test_client.headers.update(auth_headers(register_and_login(test_client)))
    return test_client


def test_list_servers_requires_authentication(client: TestClient) -> None:
    unauthenticated = TestClient(client.app)

    response = unauthenticated.get("/api/v1/mcp/servers")

    assert response.status_code == 401


def test_list_servers_returns_every_configured_server(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/servers")

    assert response.status_code == 200
    ids = {s["id"] for s in response.json()["servers"]}
    assert ids == {"test", "remote"}


def test_list_servers_never_exposes_the_credential_value(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("AGENTFORGE_TEST_REMOTE_TOKEN", "super-secret-value")

    response = client.get("/api/v1/mcp/servers")

    body = response.text
    assert "super-secret-value" not in body

    remote = next(s for s in response.json()["servers"] if s["id"] == "remote")
    assert remote["auth_type"] == "bearer"
    assert remote["auth_configured"] is True
    assert "credential_env_var" not in remote


def test_get_server_returns_404_for_unknown_server(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/servers/does-not-exist")

    assert response.status_code == 404


def test_get_server_returns_details(client: TestClient) -> None:
    response = client.get("/api/v1/mcp/servers/test")

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Test Server"
    assert body["transport"] == "stdio"
    assert body["is_remote"] is False


def test_health_check_reports_online_for_a_real_server(client: TestClient) -> None:
    response = client.post("/api/v1/mcp/servers/test/health-check")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "online"
    assert body["latency_ms"] is not None


def test_health_check_unknown_server_returns_404(client: TestClient) -> None:
    response = client.post("/api/v1/mcp/servers/does-not-exist/health-check")

    assert response.status_code == 404


def test_refresh_discovers_tools(client: TestClient) -> None:
    response = client.post("/api/v1/mcp/refresh")

    assert response.status_code == 200
    assert response.json()["refreshed_servers"] == ["test"]

    tools_response = client.get("/api/v1/mcp/servers/test/tools")
    tool_names = {t["tool_name"] for t in tools_response.json()["tools"]}
    assert tool_names == {"echo", "add", "get_test_document"}


def test_list_tools_supports_query_filtering(client: TestClient) -> None:
    client.post("/api/v1/mcp/refresh")

    response = client.get("/api/v1/mcp/tools", params={"q": "echo"})

    assert [t["tool_name"] for t in response.json()["tools"]] == ["echo"]


def test_server_tool_count_reflects_refresh(client: TestClient) -> None:
    before = client.get("/api/v1/mcp/servers/test").json()["tool_count"]
    client.post("/api/v1/mcp/refresh")
    after = client.get("/api/v1/mcp/servers/test").json()["tool_count"]

    assert before == 0
    assert after == 3
