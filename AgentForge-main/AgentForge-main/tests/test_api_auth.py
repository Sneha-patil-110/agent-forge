from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.dependencies import get_application
from backend.services.run_service import RunService
from tests.support.fake_application import FakeApplication


@pytest.fixture
def client(tmp_path: Path, db_session_factory) -> TestClient:
    fake_app = FakeApplication(
        run_service=RunService(runs_root=tmp_path / "runs"),
        db_session_factory=db_session_factory,
    )
    app = create_app()
    app.dependency_overrides[get_application] = lambda: fake_app
    return TestClient(app)


def test_register_creates_a_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "ada@example.com"
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    payload = {"email": "ada@example.com", "password": "correct-horse-battery"}
    client.post("/api/v1/auth/register", json=payload)

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 409


def test_login_returns_a_bearer_token(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "correct-horse-battery"},
    )

    response = client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "correct-horse-battery"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_rejects_wrong_password(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "correct-horse-battery"},
    )

    response = client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_me_requires_a_valid_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_me_returns_the_authenticated_user(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={"email": "ada@example.com", "password": "correct-horse-battery"},
    )
    token = client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "correct-horse-battery"}
    ).json()["access_token"]

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


def test_me_rejects_a_garbage_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401
