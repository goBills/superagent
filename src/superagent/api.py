"""
FastAPI backend for Superagent web UI.

Wraps the CLI agent in a web service with session management.
"""

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from superagent.agent import run_agent
from superagent.auth import create_token, hash_password, verify_password, verify_token
from superagent.config import HOST, PORT, get_config
from superagent.db import get_db, init_db
from superagent.models import ConversationSession, Message, User, utc_now
from superagent.rate_limit import check_rate_limit


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize product database tables on startup."""
    init_db()
    yield


# Initialize app
app = FastAPI(title="Superagent API", version="1.0.0", lifespan=lifespan)

def get_allowed_origins():
    """Build list of allowed CORS origins based on environment."""
    origins = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    config = get_config()
    # In production (Render), allow the deployment URL
    if config.RENDER_EXTERNAL_URL:
        origins.append(config.RENDER_EXTERNAL_URL)
    return origins


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_HISTORY_ITEMS = 12


init_db()


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


class AuthRequest(BaseModel):
    """Login/register request."""

    email: str
    password: str


class AuthResponse(BaseModel):
    """Login/register response."""

    ok: bool
    token: Optional[str] = None
    user_id: Optional[int] = None
    email: Optional[str] = None
    error: Optional[str] = None


class SessionSummary(BaseModel):
    """Saved conversation summary."""

    id: str
    created_at: str
    last_active: str
    expires_at: str
    message_count: int
    preview: Optional[str] = None


class SessionDetail(BaseModel):
    """Saved conversation detail."""

    id: str
    created_at: str
    last_active: str
    expires_at: str
    messages: List[Dict[str, Any]]


def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return authorization.strip()


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the current authenticated user from an Authorization header."""
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def resolve_current_user(authorization: Optional[str], db: Session) -> User:
    """Resolve the current user outside FastAPI dependency order."""
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authorization token")

    user_id = verify_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_auth_request(request: AuthRequest) -> str:
    email = _normalize_email(request.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Valid email is required")
    if not request.password or len(request.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    return email


def _message_to_history(message: Message) -> Dict[str, str]:
    return {
        "role": message.role,
        "content": message.content,
    }


def _serialize_message(message: Message) -> Dict[str, Any]:
    tools_used = []
    if message.tools_used:
        try:
            tools_used = json.loads(message.tools_used)
        except json.JSONDecodeError:
            tools_used = []
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "tools_used": tools_used,
        "created_at": message.created_at.isoformat(),
    }


def _require_admin_token(token: Optional[str]) -> None:
    """Validate admin dashboard access with an out-of-band token."""
    admin_token = get_config().ADMIN_TOKEN
    if not admin_token:
        raise HTTPException(status_code=503, detail="Admin dashboard is not configured")
    if not token or token != admin_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


def _parse_tool_names(tools_used_json: Optional[str]) -> List[str]:
    """Return readable tool names from a persisted assistant message."""
    if not tools_used_json:
        return []
    try:
        tools = json.loads(tools_used_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(tools, list):
        return []

    names = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name"):
            names.append(str(tool["name"]))
    return names


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "ok": True,
        "status": "healthy",
        "service": "Superagent API"
    }


@app.post("/auth/register", response_model=AuthResponse)
def register(request: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Register a new user and return a JWT."""
    email = _validate_auth_request(request)
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    user = User(email=email, password_hash=hash_password(request.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return AuthResponse(
        ok=True,
        token=create_token(user.id),
        user_id=user.id,
        email=user.email,
    )


@app.post("/auth/login", response_model=AuthResponse)
def login(request: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    """Log in an existing user and return a JWT."""
    email = _normalize_email(request.email)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user.last_active = utc_now()
    db.commit()

    return AuthResponse(
        ok=True,
        token=create_token(user.id),
        user_id=user.id,
        email=user.email,
    )


@app.post("/auth/logout")
def logout() -> Dict[str, Any]:
    """Token logout is client-side for the MVP."""
    return {"ok": True}


@app.post("/chat")
def chat(
    request: ChatRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """
    Chat endpoint.

    Takes a question and optional session_id.
    Returns agent response with tools used.
    Maintains persistent per-user conversation history.
    """
    # Validate question
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    current_user = resolve_current_user(authorization, db)

    if not check_rate_limit(current_user.id, db):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    now = utc_now()
    session = None
    if request.session_id:
        session = (
            db.query(ConversationSession)
            .filter(
                ConversationSession.id == request.session_id,
                ConversationSession.user_id == current_user.id,
            )
            .first()
        )
        if session is None:
            # Browser-local session ids can outlive a database reset, redeploy, or
            # sign-in change. Treat missing chat sessions as a fresh conversation
            # instead of blocking the user with a stale localStorage value.
            session = None
        elif session.expires_at < now:
            session = None

    if session is None:
        session = ConversationSession(id=str(uuid.uuid4()), user_id=current_user.id)
        db.add(session)
        db.commit()
        db.refresh(session)

    recent_messages = (
        db.query(Message)
        .filter(Message.session_id == session.id)
        .order_by(Message.id.desc())
        .limit(MAX_HISTORY_ITEMS)
        .all()
    )
    history = [_message_to_history(message) for message in reversed(recent_messages)]

    config = get_config()
    if not config.ANTHROPIC_API_KEY:
        return ChatResponse(
            ok=False,
            answer=None,
            tools_used=[],
            error="ANTHROPIC_API_KEY not configured. Set it in .env or environment.",
            session_id=session.id
        )

    try:
        # Run agent with session history
        result = run_agent(request.question, history=history)

        # Persist successful exchanges.
        if result["ok"]:
            db.add(Message(session_id=session.id, role="user", content=request.question))
            db.add(
                Message(
                    session_id=session.id,
                    role="assistant",
                    content=result.get("answer") or "",
                    tools_used=json.dumps(result.get("tools_used", [])),
                )
            )
            session.last_active = now
            current_user.last_active = now
            db.commit()

        return ChatResponse(
            ok=result["ok"],
            answer=result.get("answer"),
            tools_used=result.get("tools_used", []),
            error=result.get("error"),
            session_id=session.id
        )

    except Exception as e:
        return ChatResponse(
            ok=False,
            answer=None,
            tools_used=[],
            error=f"Agent error: {str(e)}",
            session_id=session.id
        )


@app.get("/admin")
def admin_page() -> FileResponse:
    """Serve the admin question review page."""
    static_path = os.path.join(os.path.dirname(__file__), "static", "admin.html")
    if not os.path.exists(static_path):
        raise HTTPException(status_code=404, detail="Admin page not found")
    return FileResponse(static_path, media_type="text/html")


@app.get("/admin/questions")
def admin_questions(
    token: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return recent persisted user questions for admin review."""
    _require_admin_token(token)
    limit = max(1, min(limit, 500))
    skip = max(0, skip)

    user_messages = (
        db.query(Message)
        .filter(Message.role == "user")
        .order_by(Message.created_at.desc(), Message.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    results = []
    for message in user_messages:
        session = (
            db.query(ConversationSession)
            .filter(ConversationSession.id == message.session_id)
            .first()
        )
        user = None
        if session is not None:
            user = db.query(User).filter(User.id == session.user_id).first()

        assistant_message = (
            db.query(Message)
            .filter(
                Message.session_id == message.session_id,
                Message.role == "assistant",
                Message.id > message.id,
            )
            .order_by(Message.id.asc())
            .first()
        )

        results.append(
            {
                "id": message.id,
                "user_email": user.email if user else "unknown",
                "user_id": user.id if user else None,
                "timestamp": message.created_at.isoformat(),
                "question": message.content,
                "session_id": message.session_id,
                "tools_used": _parse_tool_names(
                    assistant_message.tools_used if assistant_message else None
                ),
                "response_preview": (
                    assistant_message.content[:240] if assistant_message else None
                ),
            }
        )
    return results


@app.get("/admin/questions/summary")
def admin_questions_summary(
    token: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Return aggregate question counts for admin review."""
    _require_admin_token(token)

    total_questions = (
        db.query(func.count(Message.id))
        .filter(Message.role == "user")
        .scalar()
    )
    unique_sessions = (
        db.query(func.count(func.distinct(Message.session_id)))
        .filter(Message.role == "user")
        .scalar()
    )
    unique_users = (
        db.query(func.count(func.distinct(ConversationSession.user_id)))
        .join(Message, Message.session_id == ConversationSession.id)
        .filter(Message.role == "user")
        .scalar()
    )

    return {
        "total_questions": int(total_questions or 0),
        "unique_sessions": int(unique_sessions or 0),
        "unique_users": int(unique_users or 0),
        "timestamp": utc_now().isoformat(),
    }


@app.get("/sessions", response_model=List[SessionSummary])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[SessionSummary]:
    """List saved conversation sessions for the current user."""
    sessions = (
        db.query(ConversationSession)
        .filter(ConversationSession.user_id == current_user.id)
        .order_by(ConversationSession.last_active.desc())
        .all()
    )
    summaries = []
    for session in sessions:
        first_user_message = next(
            (message.content for message in session.messages if message.role == "user"),
            None,
        )
        summaries.append(
            SessionSummary(
                id=session.id,
                created_at=session.created_at.isoformat(),
                last_active=session.last_active.isoformat(),
                expires_at=session.expires_at.isoformat(),
                message_count=len(session.messages),
                preview=first_user_message,
            )
        )
    return summaries


@app.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    """Return a saved conversation session and its messages."""
    session = (
        db.query(ConversationSession)
        .filter(
            ConversationSession.id == session_id,
            ConversationSession.user_id == current_user.id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionDetail(
        id=session.id,
        created_at=session.created_at.isoformat(),
        last_active=session.last_active.isoformat(),
        expires_at=session.expires_at.isoformat(),
        messages=[_serialize_message(message) for message in session.messages],
    )


@app.get("/sessions/{session_id}/export", response_model=SessionDetail)
def export_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionDetail:
    """Export a saved conversation as structured JSON."""
    return get_session(session_id=session_id, current_user=current_user, db=db)


@app.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Delete a saved conversation session."""
    session = (
        db.query(ConversationSession)
        .filter(
            ConversationSession.id == session_id,
            ConversationSession.user_id == current_user.id,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)
    db.commit()
    return {"ok": True}


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
        host=HOST,
        port=PORT,
        reload=False
    )
