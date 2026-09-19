
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application, get_executor
from backend.services.run_service import RunService
from backend.state.execution_state import WorkflowStatus
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


def _client(fake_app: FakeApplication, executor: ThreadPoolExecutor) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    app.dependency_overrides[get_executor] = lambda: executor
    return TestClient(app)


def _authenticated_client(
    fake_app: FakeApplication, executor: ThreadPoolExecutor, *, email: str = "ada@example.com"
) -> TestClient:
    client = _client(fake_app, executor)
    client.headers.update(auth_headers(register_and_login(client, email=email)))
    return client


def test_get_checkpoints_returns_empty_list_for_a_run_with_no_graph_history(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.get(f"/api/v1/runs/{run_id}/checkpoints")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["checkpoints"] == []


def test_get_timeline_returns_empty_list_when_no_agent_invocations_recorded(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.get(f"/api/v1/runs/{run_id}/timeline")

    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_get_failure_detail_for_a_completed_run_has_no_recommendation(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.get(f"/api/v1/runs/{run_id}/failure")

    assert response.status_code == 200
    body = response.json()
    assert body["is_failed"] is False
    assert body["recommendation"] is None


def test_get_failure_detail_for_a_failed_run_has_a_recommendation(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.FAILED
    )
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.get(f"/api/v1/runs/{run_id}/failure")

    assert response.status_code == 200
    body = response.json()
    assert body["is_failed"] is True
    assert body["recommendation"] is not None
    assert body["recommendation"]["mode"]
    assert 0.0 <= body["recommendation"]["confidence"] <= 1.0


def test_get_run_logs_returns_empty_lines_for_an_unmatched_run(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.get(f"/api/v1/runs/{run_id}/logs")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert isinstance(body["lines"], list)


def test_retry_failed_agent_returns_202_and_invokes_application(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.FAILED
    )
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.post(f"/api/v1/runs/{run_id}/retry-agent")

    assert response.status_code == 202
    assert response.json()["run_id"] == run_id

    for _ in range(20):
        if run_id in fake_app.retry_failed_agent_calls:
            break
        time.sleep(0.05)

    assert fake_app.retry_failed_agent_calls == [run_id]


def test_restart_from_checkpoint_returns_202_and_passes_checkpoint_id(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.FAILED
    )
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.post(
        f"/api/v1/runs/{run_id}/restart-checkpoint", json={"checkpoint_id": "abc123"}
    )

    assert response.status_code == 202

    for _ in range(20):
        if fake_app.restart_from_checkpoint_calls:
            break
        time.sleep(0.05)

    assert fake_app.restart_from_checkpoint_calls == [(run_id, "abc123")]


def test_retry_agent_requires_ownership(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.FAILED
    )
    owner_client = _authenticated_client(fake_app, executor, email="ada@example.com")
    run_id = owner_client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    other_client = _authenticated_client(fake_app, executor, email="grace@example.com")
    response = other_client.post(f"/api/v1/runs/{run_id}/retry-agent")

    assert response.status_code == 404


def test_restart_project_workflow_returns_202_with_new_run_id(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    created = client.post("/api/v1/projects", json={"request": "Build a FastAPI expense tracker"})
    project_id = created.json()["project_id"]
    original_run_id = created.json()["run_id"]

    response = client.post(f"/api/v1/projects/{project_id}/restart")

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == project_id
    assert body["run_id"] != original_run_id
    assert fake_app.restart_workflow_calls == [original_run_id]


def test_duplicate_project_and_retry_creates_a_new_project(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    created = client.post("/api/v1/projects", json={"request": "Build a FastAPI expense tracker"})
    project_id = created.json()["project_id"]

    response = client.post(f"/api/v1/projects/{project_id}/duplicate")

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] != project_id
    assert fake_app.duplicate_and_retry_calls == [created.json()["run_id"]]
