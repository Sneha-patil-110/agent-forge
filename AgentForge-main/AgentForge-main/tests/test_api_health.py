from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application
from backend.services.run_service import RunService
from tests.support.fake_application import FakeApplication


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    fake_app = FakeApplication(run_service=RunService(runs_root=tmp_path / "runs"))
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    return TestClient(app)


def test_root_returns_name_and_version(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "AgentForge"
    assert "version" in body


def test_version_endpoint(client: TestClient) -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"]


def test_health_reports_database_unavailable_without_a_session_factory(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "unavailable"


def test_health_reports_database_connected_when_configured(tmp_path: Path, db_session_factory) -> None:
    fake_app = FakeApplication(
        run_service=RunService(runs_root=tmp_path / "runs"),
        db_session_factory=db_session_factory,
    )
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    client = TestClient(app)

    response = client.get("/health")

    assert response.json()["database"] == "connected"