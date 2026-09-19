from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application, get_executor
from backend.services.run_service import RunService
from tests.support.auth import auth_headers, register_and_login
from tests.support.fake_application import FakeApplication


@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


@pytest.fixture
def executor():
    pool = ThreadPoolExecutor(max_workers=2)
    yield pool
    pool.shutdown(wait=True)


def _authenticated_client(fake_app: FakeApplication, executor: ThreadPoolExecutor) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    app.dependency_overrides[get_executor] = lambda: executor
    client = TestClient(app)
    client.headers.update(auth_headers(register_and_login(client)))
    return client


def test_reliability_summary_is_empty_with_no_recorded_invocations(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/reliability/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["overall_total"] == 0
    assert body["overall_success_rate"] == 0.0
    assert body["per_agent"] == []


def test_reliability_agent_detail_rejects_unknown_agent(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/reliability/agents/not-a-real-agent")

    assert response.status_code == 404


def test_reliability_agent_detail_for_a_known_agent_with_no_data(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/reliability/agents/tester")

    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "tester"
    assert body["stats"] is None
    assert body["recent_failures"] == []


def test_reliability_summary_requires_authentication(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    app.dependency_overrides[get_executor] = lambda: executor
    client = TestClient(app)

    response = client.get("/api/v1/reliability/summary")

    assert response.status_code == 401
