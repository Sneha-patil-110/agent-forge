from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application
from backend.repositories.knowledge_repository import KnowledgeRepository
from backend.repositories.run_repository import RunRepository
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


def _seed_knowledge(run_service: RunService, db_session_factory, *, owner_id: str) -> str:
    metadata = run_service.create_run(owner_id=owner_id)
    now = datetime.now(UTC)

    with db_session_factory() as session:
        RunRepository(session).upsert(
            run_id=metadata.run_id,
            status="running",
            current_step=None,
            current_agent=None,
            error_message=None,
            test_retry_count=0,
            review_retry_count=0,
            created_at=now,
            updated_at=now,
            started_at=now,
            completed_at=None,
            user_id=uuid.UUID(owner_id),
        )
        repository = KnowledgeRepository(session)
        repository.upsert(
            run_id=metadata.run_id,
            entry_id="AD1",
            category="architecture_decision",
            title="Use repository pattern",
            content="Use the repository pattern for data access.",
            created_by="architect",
            status="active",
            source_id="AD1",
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
        repository.upsert(
            run_id=metadata.run_id,
            entry_id="CS1",
            category="coding_standard",
            title="Use snake_case",
            content="Use snake_case for functions.",
            created_by="reviewer",
            status="active",
            source_id=None,
            supersedes=None,
            created_at=now,
            updated_at=now,
        )
        session.commit()

    return metadata.run_id


def test_list_knowledge_for_a_run(client: TestClient, run_service: RunService, db_session_factory) -> None:
    run_id = _seed_knowledge(run_service, db_session_factory, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/knowledge")

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 2


def test_list_knowledge_filters_by_category(client: TestClient, run_service: RunService, db_session_factory) -> None:
    run_id = _seed_knowledge(run_service, db_session_factory, owner_id=_owner_id(client))

    response = client.get(f"/api/v1/runs/{run_id}/knowledge", params={"category": "coding_standard"})

    entries = response.json()["entries"]
    assert [entry["id"] for entry in entries] == ["CS1"]


def test_list_knowledge_for_unknown_run_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/runs/af_20260717_deadbeef/knowledge")

    assert response.status_code == 404


def test_list_knowledge_for_a_run_owned_by_someone_else_returns_404(
    client: TestClient, run_service: RunService, db_session_factory
) -> None:
    run_id = _seed_knowledge(run_service, db_session_factory, owner_id=_owner_id(client))

    other_client = TestClient(client.app)
    other_client.headers.update(auth_headers(register_and_login(other_client, email="grace@example.com")))

    response = other_client.get(f"/api/v1/runs/{run_id}/knowledge")

    assert response.status_code == 404
