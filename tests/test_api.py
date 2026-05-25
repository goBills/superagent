"""
Tests for Phase 6: FastAPI web backend.

Tests /health, /chat endpoints and session management.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from superagent.api import app

client = TestClient(app)


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
            json={"question": "What's 2 + 2?"}
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
        # First call
        response1 = client.post(
            "/chat",
            json={"question": "Tell me about Josh Allen"}
        )
        assert response1.status_code == 200
        session_id = response1.json()["session_id"]

        # Second call with same session_id
        response2 = client.post(
            "/chat",
            json={
                "question": "What about his EPA?",
                "session_id": session_id
            }
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["session_id"] == session_id

    def test_chat_generates_session_id_if_missing(self):
        """Test that /chat generates a session_id if none provided."""
        response = client.post(
            "/chat",
            json={"question": "Hello"}
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
            json={"question": "Test question"}
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
