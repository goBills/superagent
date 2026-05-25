"""
Tests for Phase 8 persistent conversation sessions.
"""

import sys
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app  # noqa: E402
from superagent.db import SessionLocal  # noqa: E402
from superagent.models import ConversationSession, Message, utc_now  # noqa: E402


client = TestClient(app)


def auth_headers() -> dict:
    response = client.post(
        "/auth/register",
        json={
            "email": f"persist-{uuid.uuid4().hex}@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def fake_agent(question, history=None):
    return {
        "ok": True,
        "answer": f"Answer for: {question}",
        "tools_used": [
            {
                "name": "fake_tool",
                "input": {"question": question},
                "result": {"ok": True},
            }
        ],
        "error": None,
    }


class FakeConfig:
    ANTHROPIC_API_KEY = "test-key"


def enable_agent(monkeypatch):
    monkeypatch.setattr("superagent.api.run_agent", fake_agent)
    monkeypatch.setattr("superagent.api.get_config", lambda: FakeConfig)


def test_session_persists_across_requests(monkeypatch):
    enable_agent(monkeypatch)
    headers = auth_headers()

    first = client.post(
        "/chat",
        json={"question": "Tell me about Josh Allen"},
        headers=headers,
    )
    assert first.status_code == 200
    session_id = first.json()["session_id"]

    second = client.post(
        "/chat",
        json={"question": "Compare him to Lamar", "session_id": session_id},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["session_id"] == session_id

    with SessionLocal() as db:
        messages = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.id)
            .all()
        )

    assert [message.role for message in messages] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert messages[0].content == "Tell me about Josh Allen"
    assert messages[2].content == "Compare him to Lamar"


def test_sessions_list_and_detail(monkeypatch):
    enable_agent(monkeypatch)
    headers = auth_headers()

    response = client.post(
        "/chat",
        json={"question": "Show the Bills schedule"},
        headers=headers,
    )
    session_id = response.json()["session_id"]

    sessions = client.get("/sessions", headers=headers)
    assert sessions.status_code == 200
    assert any(session["id"] == session_id for session in sessions.json())

    detail = client.get(f"/sessions/{session_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["id"] == session_id
    assert len(detail.json()["messages"]) == 2

    export = client.get(f"/sessions/{session_id}/export", headers=headers)
    assert export.status_code == 200
    assert export.json()["id"] == session_id


def test_delete_session(monkeypatch):
    enable_agent(monkeypatch)
    headers = auth_headers()

    response = client.post(
        "/chat",
        json={"question": "Show the Bills schedule"},
        headers=headers,
    )
    session_id = response.json()["session_id"]

    deleted = client.delete(f"/sessions/{session_id}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    detail = client.get(f"/sessions/{session_id}", headers=headers)
    assert detail.status_code == 404


def test_expired_session_creates_new_session(monkeypatch):
    enable_agent(monkeypatch)
    headers = auth_headers()

    first = client.post(
        "/chat",
        json={"question": "Tell me about Josh Allen"},
        headers=headers,
    )
    old_session_id = first.json()["session_id"]

    with SessionLocal() as db:
        session = (
            db.query(ConversationSession)
            .filter(ConversationSession.id == old_session_id)
            .first()
        )
        session.expires_at = utc_now().replace(year=2000)
        db.commit()

    second = client.post(
        "/chat",
        json={"question": "Compare him to Lamar", "session_id": old_session_id},
        headers=headers,
    )

    assert second.status_code == 200
    assert second.json()["session_id"] != old_session_id
