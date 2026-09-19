from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application, get_executor
from backend.repositories.project_repository import ProjectRepository
from backend.repositories.user_repository import UserRepository
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


def test_create_project_returns_202_with_project_and_run_ids(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    response = client.post("/api/v1/projects", json={"request": "Build a FastAPI expense tracker"})

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"].startswith("proj_")
    assert body["run_id"].startswith("af_")
    assert body["status"] == "running"


def test_create_project_requires_authentication(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _client(fake_app, executor)

    response = client.post("/api/v1/projects", json={"request": "Build a CLI tool"})

    assert response.status_code == 401


def test_create_project_rejects_empty_request_body(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.post("/api/v1/projects", json={"request": ""})

    assert response.status_code == 422


def test_continue_project_creates_a_new_run_under_the_same_project(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)

    created = client.post("/api/v1/projects", json={"request": "Build a FastAPI expense tracker"})
    project_id = created.json()["project_id"]
    first_run_id = created.json()["run_id"]

    response = client.post(f"/api/v1/projects/{project_id}/messages", json={"message": "Add authentication"})

    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == project_id
    assert body["run_id"] != first_run_id

    detail = client.get(f"/api/v1/projects/{project_id}").json()
    assert detail["run_count"] == 2
    assert detail["latest_run_id"] == body["run_id"]


def test_continue_project_requires_ownership_404_not_403(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    owner_client = _authenticated_client(fake_app, executor)
    created = owner_client.post("/api/v1/projects", json={"request": "Build a CLI tool"})
    project_id = created.json()["project_id"]

    stranger_client = _authenticated_client(fake_app, executor, email="mallory@example.com")
    response = stranger_client.post(
        f"/api/v1/projects/{project_id}/messages", json={"message": "Add tests"}
    )

    assert response.status_code == 404


def test_get_nonexistent_project_returns_404(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    response = client.get("/api/v1/projects/proj_20260719_ffffffff")

    assert response.status_code == 404


def test_list_projects_scoped_to_current_user(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    owner_client = _authenticated_client(fake_app, executor)
    owner_client.post("/api/v1/projects", json={"request": "Build a CLI tool"})

    stranger_client = _authenticated_client(fake_app, executor, email="mallory@example.com")
    stranger_client.post("/api/v1/projects", json={"request": "Build a web app"})

    response = owner_client.get("/api/v1/projects")

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 1
    assert len(body["projects"]) == 1
    assert body["projects"][0]["name"] == "Build a CLI tool"


def test_rename_project(run_service, db_session_factory, executor) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)
    created = client.post("/api/v1/projects", json={"request": "Build a CLI tool"})
    project_id = created.json()["project_id"]

    response = client.patch(f"/api/v1/projects/{project_id}", json={"name": "Renamed project"})

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed project"


def test_delete_project_soft_deletes_and_removes_from_list(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)
    created = client.post("/api/v1/projects", json={"request": "Build a CLI tool"})
    project_id = created.json()["project_id"]

    delete_response = client.delete(f"/api/v1/projects/{project_id}")
    assert delete_response.status_code == 204

    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.get("/api/v1/projects").json()["total_count"] == 0


def test_get_project_conversation_includes_the_synthesized_assistant_reply(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(
        run_service=run_service, db_session_factory=db_session_factory, start_status=WorkflowStatus.COMPLETED
    )
    client = _authenticated_client(fake_app, executor)
    created = client.post("/api/v1/projects", json={"request": "Build a FastAPI expense tracker"})
    project_id = created.json()["project_id"]

    deadline = time.monotonic() + 5.0
    messages: list = []
    while time.monotonic() < deadline:
        messages = client.get(f"/api/v1/projects/{project_id}/conversation").json()["messages"]
        if len(messages) >= 2:
            break
        time.sleep(0.02)

    assert len(messages) >= 2
    assert messages[0]["role"] == "human"
    assert messages[0]["content"] == "Build a FastAPI expense tracker"
    assert messages[1]["role"] == "ai"


def test_continue_project_returns_409_when_the_initial_run_hasnt_started(
    run_service, db_session_factory, executor
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app, executor)

    with db_session_factory() as session:
        owner_id = UserRepository(session).get_by_email("ada@example.com").id
        ProjectRepository(session).create(
            id="proj_20260719_pending1",
            user_id=owner_id,
            name="Pending project",
            initial_prompt=None,
        )
        session.commit()

    response = client.post(
        "/api/v1/projects/proj_20260719_pending1/messages", json={"message": "Add tests"}
    )
    assert response.status_code == 409
