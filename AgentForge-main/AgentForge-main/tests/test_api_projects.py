from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application
from backend.services.run_service import RunService
from tests.support.auth import auth_headers, register_and_login
from tests.support.fake_application import FakeApplication


@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


@pytest.fixture
def client(run_service: RunService, db_session_factory) -> TestClient:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    test_client = TestClient(app)
    test_client.headers.update(auth_headers(register_and_login(test_client)))
    return test_client


def _owner_id(client: TestClient) -> str:
    return client.get("/api/v1/auth/me").json()["id"]


def _seed_project_with_files(run_service: RunService, tmp_path: Path, *, owner_id: str) -> str:
    metadata = run_service.create_run(owner_id=owner_id)
    state = run_service.load_state(metadata.run_id)

    output_directory = tmp_path / "workspace" / metadata.run_id
    output_directory.mkdir(parents=True)
    (output_directory / "main.py").write_text("print('hello')\n", encoding="utf-8")

    state.project.project_name = "Expense Tracker"
    state.project.project_description = "Tracks expenses."
    state.project.status = state.project.status
    state.project.requirements = ["auth"]
    state.project.tech_stack = ["FastAPI"]
    state.project.output_directory = str(output_directory)
    state.implementation.written_files = ["main.py"]

    run_service.save_state(metadata.run_id, state)

    return metadata.run_id


def test_get_project_metadata(client: TestClient, run_service: RunService, tmp_path: Path) -> None:
    run_id = _seed_project_with_files(run_service, tmp_path, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/project")

    assert response.status_code == 200
    body = response.json()
    assert body["project_name"] == "Expense Tracker"
    assert body["requirements"] == ["auth"]


def test_list_project_files(client: TestClient, run_service: RunService, tmp_path: Path) -> None:
    run_id = _seed_project_with_files(run_service, tmp_path, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/files")

    assert response.status_code == 200
    files = response.json()["files"]
    assert [f["path"] for f in files] == ["main.py"]
    assert files[0]["size_bytes"] > 0


def test_get_project_file_content(client: TestClient, run_service: RunService, tmp_path: Path) -> None:
    run_id = _seed_project_with_files(run_service, tmp_path, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/files/main.py")

    assert response.status_code == 200
    assert response.json()["content"] == "print('hello')\n"


def test_get_project_file_rejects_path_outside_the_written_files_list(
    client: TestClient, run_service: RunService, tmp_path: Path
) -> None:
    run_id = _seed_project_with_files(run_service, tmp_path, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/files/../../../etc/passwd")

    assert response.status_code in (400, 404)


def test_get_project_file_not_found(client: TestClient, run_service: RunService, tmp_path: Path) -> None:
    run_id = _seed_project_with_files(run_service, tmp_path, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/files/does_not_exist.py")

    assert response.status_code == 404


def test_get_project_metadata_for_a_run_owned_by_someone_else_returns_404(
    client: TestClient, run_service: RunService, tmp_path: Path
) -> None:
    run_id = _seed_project_with_files(run_service, tmp_path, owner_id=_owner_id(client))

    other_client = TestClient(client.app)
    other_client.headers.update(auth_headers(register_and_login(other_client, email="grace@example.com")))

    response = other_client.get(f"/api/v1/runs/{run_id}/project")

    assert response.status_code == 404
