
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


def test_workflow_graph_node_order_matches_the_real_compiled_graph(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/workflow/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["nodes"] == [
        "analysis",
        "planner",
        "architect",
        "developer",
        "static_validation",
        "tester",
        "debugger",
        "reviewer",
        "documentation",
    ]


def test_workflow_graph_includes_developer_to_static_validation_edge(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    body = client.get("/api/v1/workflow/graph").json()
    edge_pairs = {(edge["source"], edge["target"]) for edge in body["edges"]}

    assert ("developer", "static_validation") in edge_pairs
    assert ("static_validation", "tester") in edge_pairs
    assert ("static_validation", "debugger") in edge_pairs
    assert ("developer", "tester") not in edge_pairs
    assert ("developer", "debugger") not in edge_pairs


def test_workflow_graph_repair_nodes_include_debugger_and_reviewer(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    body = client.get("/api/v1/workflow/graph").json()

    assert set(body["repair_nodes"]) == {"debugger", "reviewer"}


def test_workflow_graph_requires_authentication(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    app.dependency_overrides[get_executor] = lambda: executor
    client = TestClient(app)

    response = client.get("/api/v1/workflow/graph")

    assert response.status_code == 401
