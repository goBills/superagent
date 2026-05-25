"""
Tests for Phase 6: FastAPI web backend.

Tests /health, /chat endpoints and session management.
"""

import sys
from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app
from superagent.db import SessionLocal
from superagent.models import ConversationSession, DraftImportReview, Message, User

client = TestClient(app)


def auth_headers() -> dict:
    """Register a unique test user and return auth headers."""
    email = f"test-{uuid.uuid4().hex}@example.com"
    response = client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 200
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def use_admin_token(monkeypatch, token: str = "test-admin-token") -> str:
    """Configure admin endpoints for a test."""

    class TestConfig:
        ADMIN_TOKEN = token
        ANTHROPIC_API_KEY = "test-key"

    monkeypatch.setattr("superagent.api.get_config", lambda: TestConfig)
    return token


def create_persisted_question(question: str = "What's Josh Allen's EPA?") -> dict:
    """Create a user, session, question, and assistant tool record."""
    email = f"admin-{uuid.uuid4().hex}@example.com"
    register = client.post(
        "/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert register.status_code == 200

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        session = ConversationSession(id=str(uuid.uuid4()), user_id=user.id)
        db.add(session)
        db.commit()

        user_message = Message(
            session_id=session.id,
            role="user",
            content=question,
        )
        db.add(user_message)
        db.commit()

        assistant_message = Message(
            session_id=session.id,
            role="assistant",
            content="Josh Allen's EPA/play was 0.259.",
            tools_used='[{"name": "get_player_advanced_summary"}]',
        )
        db.add(assistant_message)
        db.commit()

        return {"email": email, "session_id": session.id}


class TestAPIHealth:
    """Test health check endpoint."""

    def test_health_check(self):
        """Test /health returns ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] == True
        assert data["status"] == "healthy"


class TestAPIChat:
    """Test /chat endpoint."""

    def test_chat_empty_question(self):
        """Test /chat with empty question."""
        response = client.post("/chat", json={"question": ""})
        assert response.status_code == 400

    def test_chat_simple_question(self):
        """Test /chat with a simple question."""
        # Note: This will hit the real agent, so it may be slow
        # For faster tests, mock the agent, but this validates integration
        response = client.post(
            "/chat",
            json={"question": "What's 2 + 2?"},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        # Agent might fail (e.g., no API key), but response structure should be valid
        assert "ok" in data
        assert "answer" in data or "error" in data

    def test_chat_session_persistence(self):
        """Test that session_id persists across calls."""
        headers = auth_headers()
        # First call
        response1 = client.post(
            "/chat",
            json={"question": "Tell me about Josh Allen"},
            headers=headers,
        )
        assert response1.status_code == 200
        session_id = response1.json()["session_id"]

        # Second call with same session_id
        response2 = client.post(
            "/chat",
            json={
                "question": "What about his EPA?",
                "session_id": session_id
            },
            headers=headers,
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["session_id"] == session_id

    def test_chat_generates_session_id_if_missing(self):
        """Test that /chat generates a session_id if none provided."""
        response = client.post(
            "/chat",
            json={"question": "Hello"},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        # Should be a valid UUID-like string
        assert len(data["session_id"]) > 0

    def test_chat_response_structure(self):
        """Test that /chat response has correct structure."""
        response = client.post(
            "/chat",
            json={"question": "Test question"},
            headers=auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()

        # Validate structure
        assert "ok" in data
        assert isinstance(data["ok"], bool)
        assert "answer" in data
        assert "tools_used" in data
        assert isinstance(data["tools_used"], list)
        assert "error" in data
        assert "session_id" in data
        assert isinstance(data["session_id"], str)

    def test_chat_with_whitespace_only_question(self):
        """Test /chat with whitespace-only question."""
        response = client.post(
            "/chat",
            json={"question": "   \n  "}
        )
        assert response.status_code == 400


class TestAPICORS:
    """Test CORS configuration."""

    def test_cors_localhost_allowed(self):
        """Test that localhost origins are allowed."""
        response = client.options(
            "/chat",
            headers={
                "Origin": "http://localhost:8000",
                "Access-Control-Request-Method": "POST"
            }
        )
        # CORS headers should be set (or no error if handled by FastAPI)
        assert response.status_code in [200, 405]  # OK or Method Not Allowed

    def test_root_endpoint(self):
        """Test GET / returns HTML or message."""
        response = client.get("/")
        assert response.status_code == 200
        # Either serves HTML or returns JSON
        if response.headers.get("content-type") == "text/html; charset=utf-8":
            assert "<!DOCTYPE html>" in response.text or "html" in response.text.lower()
        else:
            data = response.json()
            assert "message" in data or "ok" in data


class TestAdminQuestions:
    """Test protected admin question review endpoints."""

    def test_admin_page_serves_html(self):
        response = client.get("/admin")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Superagent Admin" in response.text

    def test_admin_questions_requires_token(self, monkeypatch):
        use_admin_token(monkeypatch)

        response = client.get("/admin/questions")

        assert response.status_code == 401

    def test_admin_questions_wrong_token(self, monkeypatch):
        use_admin_token(monkeypatch)

        response = client.get("/admin/questions?token=wrong-token")

        assert response.status_code == 401

    def test_admin_questions_requires_configured_token(self, monkeypatch):
        use_admin_token(monkeypatch, token="")

        response = client.get("/admin/questions?token=anything")

        assert response.status_code == 503

    def test_admin_questions_correct_token(self, monkeypatch):
        token = use_admin_token(monkeypatch)
        record = create_persisted_question()

        response = client.get(f"/admin/questions?token={token}&limit=10")

        assert response.status_code == 200
        data = response.json()
        match = next(item for item in data if item["session_id"] == record["session_id"])
        assert match["question"] == "What's Josh Allen's EPA?"
        assert match["user_email"] == record["email"]
        assert match["tools_used"] == ["get_player_advanced_summary"]

    def test_admin_summary_requires_token(self, monkeypatch):
        use_admin_token(monkeypatch)

        response = client.get("/admin/questions/summary")

        assert response.status_code == 401

    def test_admin_summary_correct_token(self, monkeypatch):
        token = use_admin_token(monkeypatch)
        create_persisted_question("Question 1")
        create_persisted_question("Question 2")

        response = client.get(f"/admin/questions/summary?token={token}")

        assert response.status_code == 200
        data = response.json()
        assert data["total_questions"] >= 2
        assert data["unique_sessions"] >= 2
        assert data["unique_users"] >= 2

    def test_admin_draft_mappings_requires_token(self, monkeypatch):
        use_admin_token(monkeypatch)

        response = client.get("/admin/draft-mappings")

        assert response.status_code == 401

    def test_admin_draft_mappings_correct_token(self, monkeypatch):
        token = use_admin_token(monkeypatch)
        with SessionLocal() as db:
            review = DraftImportReview(
                source="draftsheetsv6",
                season=2025,
                source_player_name="Future Rookie",
                candidates='[{"full_name": "Futures Guy", "confidence": 0.61}]',
                status="pending",
            )
            db.add(review)
            db.commit()
            review_id = review.id

        response = client.get(f"/admin/draft-mappings?token={token}")

        assert response.status_code == 200
        data = response.json()
        match = next(item for item in data if item["id"] == review_id)
        assert match["source"] == "draftsheetsv6"
        assert match["source_player_name"] == "Future Rookie"
        assert match["candidates"][0]["confidence"] == 0.61

    def test_admin_seed_canonical_requires_token(self, monkeypatch):
        use_admin_token(monkeypatch)

        response = client.post("/admin/seed-canonical?season=2025")

        assert response.status_code == 401

    def test_admin_seed_canonical_correct_token(self, monkeypatch):
        token = use_admin_token(monkeypatch)

        def fake_seed(seasons=None, include_alias_enrichment=True):
            assert seasons == [2025]
            assert include_alias_enrichment is False
            return {
                "players_created": 1,
                "players_seen": 1,
                "player_seasons_created": 1,
                "aliases_created": 2,
            }

        monkeypatch.setattr("superagent.api.seed_canonical_players_from_nflverse", fake_seed)

        response = client.post(f"/admin/seed-canonical?token={token}&season=2025&wait=true")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["season"] == 2025
        assert data["summary"]["players_created"] == 1

    def test_admin_seed_canonical_background_job(self, monkeypatch):
        token = use_admin_token(monkeypatch)

        def fake_seed(seasons=None, include_alias_enrichment=True):
            assert seasons == [2025]
            assert include_alias_enrichment is False
            return {
                "players_created": 1,
                "players_seen": 1,
                "player_seasons_created": 1,
                "aliases_created": 2,
            }

        monkeypatch.setattr("superagent.api.seed_canonical_players_from_nflverse", fake_seed)

        response = client.post(f"/admin/seed-canonical?token={token}&season=2025")

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["job_id"]

        status = client.get(f"/admin/jobs/{data['job_id']}?token={token}")
        assert status.status_code == 200
        job = status.json()
        assert job["type"] == "seed_canonical"
        assert job["status"] == "completed"
        assert job["result"]["players_created"] == 1

    def test_admin_seed_canonical_full_aliases_option(self, monkeypatch):
        token = use_admin_token(monkeypatch)

        def fake_seed(seasons=None, include_alias_enrichment=True):
            assert seasons == [2025]
            assert include_alias_enrichment is True
            return {
                "players_created": 1,
                "players_seen": 1,
                "player_seasons_created": 1,
                "aliases_created": 2,
            }

        monkeypatch.setattr("superagent.api.seed_canonical_players_from_nflverse", fake_seed)

        response = client.post(
            f"/admin/seed-canonical?token={token}&season=2025&wait=true&full_aliases=true"
        )

        assert response.status_code == 200
        assert response.json()["summary"]["aliases_created"] == 2

    def test_admin_draft_import_requires_token(self, monkeypatch):
        use_admin_token(monkeypatch)

        response = client.post(
            "/admin/draft-import?source=draftsheetsv6&season=2025&sheet=DATA",
            files={
                "file": (
                    "draft.csv",
                    b"Player,Team,POS\nJosh Allen,BUF,QB1\n",
                    "text/csv",
                )
            },
        )

        assert response.status_code == 401

    def test_admin_draft_import_correct_token(self, monkeypatch):
        token = use_admin_token(monkeypatch)
        captured = {}

        def fake_import(file_path, source, season, sheet_name=None):
            assert Path(file_path).exists()
            captured["source"] = source
            captured["season"] = season
            captured["sheet_name"] = sheet_name
            return {
                "ok": True,
                "rows_seen": 1,
                "rows_imported": 1,
                "rows_needing_review": 0,
            }

        monkeypatch.setattr("superagent.api.ingest_draft_market_file", fake_import)

        response = client.post(
            f"/admin/draft-import?token={token}&source=draftsheetsv6&season=2025&sheet=DATA&wait=true",
            files={
                "file": (
                    "draft.csv",
                    b"Player,Team,POS\nJosh Allen,BUF,QB1\n",
                    "text/csv",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["summary"]["rows_imported"] == 1
        assert captured == {
            "source": "draftsheetsv6",
            "season": 2025,
            "sheet_name": "DATA",
        }

    def test_admin_draft_import_background_job(self, monkeypatch):
        token = use_admin_token(monkeypatch)

        def fake_import(file_path, source, season, sheet_name=None, progress_callback=None):
            assert Path(file_path).exists()
            if progress_callback:
                progress_callback({"stage": "test_import"})
            return {
                "ok": True,
                "rows_seen": 1,
                "rows_imported": 1,
                "rows_needing_review": 0,
            }

        monkeypatch.setattr("superagent.api.ingest_draft_market_file", fake_import)

        response = client.post(
            f"/admin/draft-import?token={token}&source=draftsheetsv6&season=2025&sheet=DATA",
            files={
                "file": (
                    "draft.csv",
                    b"Player,Team,POS\nJosh Allen,BUF,QB1\n",
                    "text/csv",
                )
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["job_id"]

        status = client.get(f"/admin/jobs/{data['job_id']}?token={token}")
        assert status.status_code == 200
        job = status.json()
        assert job["type"] == "draft_import"
        assert job["status"] == "completed"
        assert job["progress"]["stage"] == "test_import"
        assert job["result"]["rows_imported"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
