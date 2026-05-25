"""
FastAPI backend for Superagent web UI.

Wraps the CLI agent in a web service with session management.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uuid
import os

from superagent.agent import run_agent
from superagent.config import get_config

# Initialize app
app = FastAPI(title="Superagent API", version="1.0.0")

# Add CORS middleware for localhost only
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory session storage
# Key: session_id, Value: list of recent messages (max 12)
SESSIONS: Dict[str, List[Dict[str, str]]] = {}
MAX_HISTORY_ITEMS = 12


class ChatRequest(BaseModel):
    """Request body for /chat endpoint."""
    question: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response body for /chat endpoint."""
    ok: bool
    answer: Optional[str] = None
    tools_used: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
    session_id: str


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "ok": True,
        "status": "healthy",
        "service": "Superagent API"
    }


@app.post("/chat")
def chat(request: ChatRequest) -> ChatResponse:
    """
    Chat endpoint.

    Takes a question and optional session_id.
    Returns agent response with tools used.
    Maintains per-session conversation history.
    """
    # Validate question
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    # Create or retrieve session
    session_id = request.session_id or str(uuid.uuid4())
    history = SESSIONS.get(session_id, [])

    config = get_config()
    if not config.ANTHROPIC_API_KEY:
        return ChatResponse(
            ok=False,
            answer=None,
            tools_used=[],
            error="ANTHROPIC_API_KEY not configured. Set it in .env or environment.",
            session_id=session_id
        )

    try:
        # Run agent with session history
        result = run_agent(request.question, history=history)

        # Update session history with new exchange
        if result["ok"]:
            # Add user turn
            history.append({
                "role": "user",
                "content": request.question
            })
            # Add assistant turn
            history.append({
                "role": "assistant",
                "content": result["answer"]
            })
            # Cap at MAX_HISTORY_ITEMS
            history = history[-MAX_HISTORY_ITEMS:]
            SESSIONS[session_id] = history

        return ChatResponse(
            ok=result["ok"],
            answer=result.get("answer"),
            tools_used=result.get("tools_used", []),
            error=result.get("error"),
            session_id=session_id
        )

    except Exception as e:
        return ChatResponse(
            ok=False,
            answer=None,
            tools_used=[],
            error=f"Agent error: {str(e)}",
            session_id=session_id
        )


@app.get("/")
def root():
    """Serve the web UI."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(static_path):
        return FileResponse(static_path, media_type="text/html")
    return {
        "message": "Superagent API",
        "status": "running",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "superagent.api:app",
        host="127.0.0.1",
        port=8000,
        reload=False
    )
