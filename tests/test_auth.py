"""
Tests for Phase 8 auth and rate limiting.
"""

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app  # noqa: E402
from superagent.auth import verify_token  # noqa: E402
from superagent.config import RATE_LIMIT_PER_HOUR  # noqa: E402
from superagent.db import SessionLocal  # noqa: E402
from superagent.models import RateLimit  # noqa: E402
from superagent.rate_limit import current_hour  # noqa: E402


client = TestClient(app)


def unique_email() -> str:
    return f"phase8-{uuid.uuid4().hex}@example.com"


def register_user(email: str | None = None, password: str = "password123") -> dict:
    response = client.post(
        "/auth/register",
        json={"email": email or unique_email(), "password": password},
    )
    assert response.status_code == 200
    return response.json()


def test_register_new_user_returns_token():
    data = register_user()

    assert data["ok"] is True
    assert data["token"]
    assert isinstance(data["user_id"], int)
    assert verify_token(data["token"]) == data["user_id"]


def test_register_duplicate_user_rejected():
    email = unique_email()
    register_user(email=email)

    response = client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )

    assert response.status_code == 409


def test_login_existing_user():
    email = unique_email()
    register_user(email=email, password="password123")

    response = client.post(
        "/auth/login",
        json={"email": email, "password": "password123"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["token"]


def test_login_wrong_password():
    email = unique_email()
    register_user(email=email, password="password123")

    response = client.post(
        "/auth/login",
        json={"email": email, "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_chat_requires_auth():
    response = client.post("/chat", json={"question": "Hello"})

    assert response.status_code == 401


def test_rate_limit_enforcement(monkeypatch):
    data = register_user()
    token = data["token"]
    user_id = data["user_id"]

    monkeypatch.setattr(
        "superagent.api.run_agent",
        lambda question, history=None: {
            "ok": True,
            "answer": "ok",
            "tools_used": [],
            "error": None,
        },
    )

    with SessionLocal() as db:
        db.add(
            RateLimit(
                user_id=user_id,
                hour=current_hour(),
                request_count=RATE_LIMIT_PER_HOUR,
            )
        )
        db.commit()

    response = client.post(
        "/chat",
        json={"question": "Hello"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 429
