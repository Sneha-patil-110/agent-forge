from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application, get_executor
from backend.core.config import settings
from backend.repositories.run_repository import RunRepository
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


def _authenticated_client(fake_app: FakeApplication, executor: ThreadPoolExecutor) -> TestClient:
    client = _client(fake_app, executor)
    client.headers.update(auth_headers(register_and_login(client)))
    return client


def test_create_run_returns_202_with_the_captured_run_id(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.post("/api/v1/runs", json={"request": "Build a FastAPI expense tracker"})

    assert response.status_code == 202
    body = response.json()
    assert body["run_id"].startswith("af_")
    assert body["status"] == "running"
    assert fake_app.start_run_calls == ["Build a FastAPI expense tracker"]


def test_create_run_rejects_empty_request_body(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.post("/api/v1/runs", json={"request": ""})

    assert response.status_code == 422


def test_create_run_requires_authentication(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _client(fake_app, executor)

    response = client.post("/api/v1/runs", json={"request": "Build a CLI tool"})

    assert response.status_code == 401


def test_get_run_returns_detail_after_completion(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    create_response = client.post("/api/v1/runs", json={"request": "Build a CLI tool"})
    run_id = create_response.json()["run_id"]

    detail_response = client.get(f"/api/v1/runs/{run_id}")

    assert detail_response.status_code == 200
    body = detail_response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "completed"


def test_get_run_returns_404_for_a_run_owned_by_someone_else(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    owner_client = _authenticated_client(fake_app, executor)
    run_id = owner_client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    other_client = _client(fake_app, executor)
    other_client.headers.update(auth_headers(register_and_login(other_client, email="grace@example.com")))

    response = other_client.get(f"/api/v1/runs/{run_id}")

    assert response.status_code == 404


def test_get_run_status_for_unknown_run_returns_404(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/runs/af_20260717_deadbeef/status")

    assert response.status_code == 404
    assert response.json()["error"]["type"] == "RunNotFoundError"


def test_get_run_status_for_invalid_run_id_returns_400(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/runs/not-a-real-run-id/status")

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "InvalidRunIdError"


def test_resume_already_completed_run_returns_immediately_without_background_work(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.post(f"/api/v1/runs/{run_id}/resume")

    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    assert fake_app.resume_run_calls == []


def test_resume_returns_409_when_a_resume_is_already_in_flight(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.RUNNING
    )
    client = _authenticated_client(fake_app, executor)
    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    fake_app.mark_resuming(run_id)

    response = client.post(f"/api/v1/runs/{run_id}/resume")

    assert response.status_code == 409
    assert fake_app.resume_run_calls == []


def test_resume_guard_clears_after_the_background_resume_completes(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.RUNNING
    )
    client = _authenticated_client(fake_app, executor)
    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]

    response = client.post(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 202

    deadline = time.monotonic() + 5.0
    while fake_app.is_resuming(run_id) and time.monotonic() < deadline:
        time.sleep(0.02)

    assert fake_app.is_resuming(run_id) is False
    assert fake_app.resume_run_calls == [run_id]


def test_resume_unknown_run_returns_404(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.post("/api/v1/runs/af_20260717_deadbeef/resume")

    assert response.status_code == 404


def _wait_until_terminal(client: TestClient, run_id: str, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        status_response = client.get(f"/api/v1/runs/{run_id}/status")
        if status_response.json()["status"] in ("completed", "failed"):
            return
        time.sleep(0.02)

    raise AssertionError(f"Run {run_id} did not reach a terminal status within {timeout}s")


def test_list_runs_reads_from_the_database(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    run_id_one = client.post("/api/v1/runs", json={"request": "Build app one"}).json()["run_id"]
    run_id_two = client.post("/api/v1/runs", json={"request": "Build app two"}).json()["run_id"]
    _wait_until_terminal(client, run_id_one)
    _wait_until_terminal(client, run_id_two)

    deadline = time.monotonic() + 5.0
    runs: list = []
    while time.monotonic() < deadline:
        runs = client.get("/api/v1/runs").json()["runs"]
        if len(runs) == 2 and all(run["status"] == "completed" for run in runs):
            break
        time.sleep(0.02)

    assert len(runs) == 2
    assert all(run["status"] == "completed" for run in runs)


def test_list_runs_only_returns_the_current_users_runs(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client_one = _authenticated_client(fake_app, executor)
    run_id = client_one.post("/api/v1/runs", json={"request": "Build app one"}).json()["run_id"]
    _wait_until_terminal(client_one, run_id)

    client_two = _client(fake_app, executor)
    client_two.headers.update(auth_headers(register_and_login(client_two, email="grace@example.com")))

    response = client_two.get("/api/v1/runs")

    assert response.status_code == 200
    assert response.json()["runs"] == []


def test_list_runs_reports_total_count_and_has_more_for_pagination(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    for i in range(3):
        run_id = client.post("/api/v1/runs", json={"request": f"Build app {i}"}).json()["run_id"]
        _wait_until_terminal(client, run_id)

    response = client.get("/api/v1/runs", params={"limit": 2, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert len(body["runs"]) == 2
    assert body["total_count"] == 3
    assert body["has_more"] is True

    last_page = client.get("/api/v1/runs", params={"limit": 2, "offset": 2})
    assert len(last_page.json()["runs"]) == 1
    assert last_page.json()["has_more"] is False


def test_list_runs_rejects_an_unknown_status_filter(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/runs", params={"status_filter": "cancelled"})

    assert response.status_code == 422


def test_list_runs_without_a_database_configured_returns_503(run_service, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=None)
    client = _client(fake_app, executor)

    response = client.get("/api/v1/runs")

    assert response.status_code == 503


def test_create_run_is_rate_limited_per_user(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    for _ in range(settings.RATE_LIMIT_RUN_CREATION_PER_MINUTE):
        response = client.post("/api/v1/runs", json={"request": "Build a CLI tool"})
        assert response.status_code == 202

    response = client.post("/api/v1/runs", json={"request": "One too many"})

    assert response.status_code == 429


def test_create_run_rate_limit_is_scoped_per_user(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client_one = _authenticated_client(fake_app, executor)

    for _ in range(settings.RATE_LIMIT_RUN_CREATION_PER_MINUTE):
        client_one.post("/api/v1/runs", json={"request": "Build a CLI tool"})

    client_two = _client(fake_app, executor)
    client_two.headers.update(auth_headers(register_and_login(client_two, email="grace@example.com")))

    response = client_two.post("/api/v1/runs", json={"request": "Build a CLI tool"})

    assert response.status_code == 202


def test_resume_run_is_rate_limited_per_user(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)
    run_id = client.post("/api/v1/runs", json={"request": "Build a CLI tool"}).json()["run_id"]
    _wait_until_terminal(client, run_id)

    for _ in range(settings.RATE_LIMIT_RUN_RESUME_PER_MINUTE):
        response = client.post(f"/api/v1/runs/{run_id}/resume")
        assert response.status_code == 202

    response = client.post(f"/api/v1/runs/{run_id}/resume")

    assert response.status_code == 429


def test_concurrent_create_run_calls_each_get_their_own_run_id(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    responses = [
        client.post("/api/v1/runs", json={"request": f"Build app {i}"})
        for i in range(5)
    ]

    run_ids = [response.json()["run_id"] for response in responses]
    assert len(set(run_ids)) == 5
