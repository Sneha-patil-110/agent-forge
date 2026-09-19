from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application
from backend.events.event_types import EventType, WorkflowEvent
from backend.repositories.event_repository import EventRepository
from backend.repositories.run_repository import RunRepository
from backend.services.run_service import RunService
from tests.support.auth import auth_headers, register_and_login
from tests.support.fake_application import FakeApplication


@pytest.fixture
def run_service(tmp_path: Path) -> RunService:
    return RunService(runs_root=tmp_path / "runs")


def _authenticated_client(fake_app: FakeApplication) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    client = TestClient(app)
    client.headers.update(auth_headers(register_and_login(client)))
    return client


def test_stream_unknown_run_returns_404(run_service: RunService, db_session_factory) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app)

    response = client.get("/api/v1/runs/af_20260717_deadbeef/events")

    assert response.status_code == 404


def test_stream_replays_history_from_the_database(run_service: RunService, db_session_factory) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app)
    owner_id = client.get("/api/v1/auth/me").json()["id"]

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
        event_repository = EventRepository(session)
        event_repository.add(
            run_id=metadata.run_id,
            event_type="workflow_started",
            agent=None,
            message=None,
            event_metadata={},
            timestamp=now,
        )
        event_repository.add(
            run_id=metadata.run_id,
            event_type="agent_started",
            agent="analysis",
            message=None,
            event_metadata={},
            timestamp=now,
        )
        event_repository.add(
            run_id=metadata.run_id,
            event_type="workflow_completed",
            agent=None,
            message=None,
            event_metadata={},
            timestamp=now,
        )
        session.commit()

    lines: list[str] = []

    with client.stream("GET", f"/api/v1/runs/{metadata.run_id}/events") as response:
        assert response.status_code == 200

        for raw_line in response.iter_lines():
            if raw_line.startswith("data: "):
                lines.append(raw_line[len("data: ") :])

    payloads = [json.loads(line) for line in lines]
    assert [payload["event_type"] for payload in payloads] == [
        "workflow_started",
        "agent_started",
        "workflow_completed",
    ]


def test_stream_delivers_live_events_emitted_after_connecting(run_service: RunService, db_session_factory) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    client = _authenticated_client(fake_app)
    owner_id = client.get("/api/v1/auth/me").json()["id"]

    metadata = run_service.create_run(owner_id=owner_id)

    def _emit_shortly_after_connecting() -> None:
        time.sleep(0.3)
        fake_app.event_dispatcher.emit(
            WorkflowEvent(event_type=EventType.AGENT_STARTED, run_id=metadata.run_id, agent=None)
        )
        fake_app.event_dispatcher.emit(
            WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id=metadata.run_id)
        )

    threading.Thread(target=_emit_shortly_after_connecting, daemon=True).start()

    lines: list[str] = []

    with client.stream("GET", f"/api/v1/runs/{metadata.run_id}/events") as response:
        assert response.status_code == 200

        for raw_line in response.iter_lines():
            if raw_line.startswith("data: "):
                lines.append(json.loads(raw_line[len("data: ") :]))

    assert [payload["event_type"] for payload in lines] == ["agent_started", "workflow_completed"]


def test_stream_for_a_run_owned_by_someone_else_returns_404(run_service: RunService, db_session_factory) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    owner_client = _authenticated_client(fake_app)
    owner_id = owner_client.get("/api/v1/auth/me").json()["id"]
    metadata = run_service.create_run(owner_id=owner_id)

    other_client = TestClient(owner_client.app)
    other_client.headers.update(auth_headers(register_and_login(other_client, email="grace@example.com")))

    response = other_client.get(f"/api/v1/runs/{metadata.run_id}/events")

    assert response.status_code == 404


def test_stream_accepts_a_token_query_parameter_since_eventsource_cannot_set_headers(
    run_service: RunService, db_session_factory
) -> None:
    fake_app = FakeApplication(run_service=run_service, db_session_factory=db_session_factory)
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    setup_client = TestClient(app)
    token = register_and_login(setup_client)
    owner_id = setup_client.get("/api/v1/auth/me", headers=auth_headers(token)).json()["id"]

    metadata = run_service.create_run(owner_id=owner_id)

    def _emit_shortly_after_connecting() -> None:
        time.sleep(0.3)
        fake_app.event_dispatcher.emit(
            WorkflowEvent(event_type=EventType.WORKFLOW_COMPLETED, run_id=metadata.run_id)
        )

    threading.Thread(target=_emit_shortly_after_connecting, daemon=True).start()

    no_auth_client = TestClient(app)
    lines: list[str] = []

    with no_auth_client.stream(
        "GET", f"/api/v1/runs/{metadata.run_id}/events", params={"token": token}
    ) as response:
        assert response.status_code == 200

        for raw_line in response.iter_lines():
            if raw_line.startswith("data: "):
                lines.append(json.loads(raw_line[len("data: ") :]))

    assert [payload["event_type"] for payload in lines] == ["workflow_completed"]
