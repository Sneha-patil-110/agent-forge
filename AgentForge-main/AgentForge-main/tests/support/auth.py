
from __future__ import annotations

from fastapi.testclient import TestClient

_DEFAULT_PASSWORD = "correct-horse-battery"


def register_and_login(
    client: TestClient, *, email: str = "ada@example.com", password: str = _DEFAULT_PASSWORD
) -> str:

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
