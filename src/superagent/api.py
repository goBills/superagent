"""
FastAPI backend for Superagent web UI.

Wraps the CLI agent in a web service with session management.
"""

import json
import os
import tempfile
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from superagent.agent import run_agent
from superagent.auth import create_token, hash_password, verify_password, verify_token
from superagent.canonical_resolution import resolve_to_canonical, seed_canonical_players_from_nflverse
from superagent.config import HOST, PORT, get_config
from superagent.data.ingest_draft_sheets import DraftIngestionError, ingest_draft_market_file
from superagent.db import get_db, init_db
from superagent.espn_integration import ingest_espn_league
from superagent.models import (
    ConversationSession,
    DraftImportReview,
    DraftPlayerMarket,
    League,
    LeagueDraftPick,
    LeagueRosterPlayer,
    LeagueSettings,
    Message,
    User,
    utc_now,
)
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
ADMIN_JOBS: Dict[str, Dict[str, Any]] = {}


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


class LeagueSettingsPayload(BaseModel):
    """Fantasy league scoring and roster settings payload."""

    ppr_type: str = "ppr"
    num_teams: int = 12
    roster_spots: int = 16
    qb_slots: int = 1
    rb_slots: int = 2
    wr_slots: int = 2
    te_slots: int = 1
    flex_slots: int = 1
    superflex_slots: int = 0
    bench_spots: int = 6
    taxi_spots: int = 0
    passing_td_points: float = 4.0
    rushing_td_points: float = 6.0
    receiving_td_points: float = 6.0
    pass_yards_per_point: float = 25.0
    rush_yards_per_point: float = 10.0
    receiving_yards_per_point: float = 10.0


class LeagueRequest(BaseModel):
    """Create/update league request."""

    league_name: str
    league_type: str = "snake"
    settings: LeagueSettingsPayload = Field(default_factory=LeagueSettingsPayload)


class LeagueResponse(BaseModel):
    """League response."""

    id: int
    league_name: str
    league_type: str
    created_at: str
    updated_at: str
    settings: Dict[str, Any]


class AdminDefaultLeagueRequest(BaseModel):
    """Admin helper request for creating a default league for an existing user."""

    user_email: str
    league_name: str
    league_type: str = "snake"
    num_teams: int = 12
    roster_spots: int = 16
    ppr_type: str = "ppr"
    passing_td_points: float = 4.0
    rushing_td_points: float = 6.0
    receiving_td_points: float = 6.0
    passing_yards_per_point: float = 25.0
    rushing_yards_per_point: float = 10.0
    receiving_yards_per_point: float = 10.0


class ESPNLeagueSyncRequest(BaseModel):
    """Sync ESPN league request."""

    espn_league_id: int
    season: int
    espn_s2: Optional[str] = None
    swid: Optional[str] = None


class DraftPickRequest(BaseModel):
    """Record one live draft pick."""

    pick_number: int
    player_name: str
    team_name: Optional[str] = None
    season: Optional[int] = None
    source: Optional[str] = None


class DraftPickResponse(BaseModel):
    """Persisted live draft pick response."""

    id: int
    league_id: int
    season: int
    round_num: int
    pick_num: int
    fantasy_team_name: Optional[str] = None
    source_player_name: str
    position: Optional[str] = None
    canonical_player_id: Optional[str] = None
    mapping_status: str
    created_at: str


class DraftBoardResponse(BaseModel):
    """Live draft board response."""

    league_id: int
    season: int
    picks: List[Dict[str, Any]]
    summary: Optional[Dict[str, Any]] = None


class DraftBulkPickItem(BaseModel):
    """One pick within a bulk paste of the draft board."""

    pick_number: int
    player_name: str
    team_name: Optional[str] = None
    is_mine: bool = False


class DraftBulkRequest(BaseModel):
    """Bulk-record many draft picks in a single request (e.g. pasted board)."""

    picks: List[DraftBulkPickItem]
    season: Optional[int] = None
    source: Optional[str] = None


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


def _create_admin_job(job_type: str, payload: Dict[str, Any]) -> str:
    """Create an in-memory admin job record for long-running operator tasks."""
    job_id = str(uuid.uuid4())
    ADMIN_JOBS[job_id] = {
        "id": job_id,
        "type": job_type,
        "status": "queued",
        "payload": payload,
        "result": None,
        "error": None,
        "progress": None,
        "created_at": utc_now().isoformat(),
        "started_at": None,
        "completed_at": None,
    }
    return job_id


def _run_seed_canonical_job(
    job_id: str,
    seasons: Optional[List[int]],
    include_alias_enrichment: bool,
) -> None:
    """Run canonical seeding outside the request/response cycle."""
    job = ADMIN_JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = utc_now().isoformat()
    try:
        job["result"] = seed_canonical_players_from_nflverse(
            seasons=seasons,
            include_alias_enrichment=include_alias_enrichment,
        )
        job["status"] = "completed"
    except Exception as exc:
        job["error"] = str(exc)
        job["status"] = "failed"
    finally:
        job["completed_at"] = utc_now().isoformat()


def _run_draft_import_job(
    job_id: str,
    file_path: str,
    source: str,
    season: int,
    sheet: Optional[str],
) -> None:
    """Run DraftSheets import outside the request/response cycle."""
    job = ADMIN_JOBS[job_id]
    job["status"] = "running"
    job["started_at"] = utc_now().isoformat()
    try:
        def update_progress(progress: Dict[str, Any]) -> None:
            job["progress"] = {
                **progress,
                "updated_at": utc_now().isoformat(),
            }
            print(f"Draft import job {job_id}: {progress}", flush=True)

        job["result"] = ingest_draft_market_file(
            file_path=file_path,
            source=source,
            season=season,
            sheet_name=sheet,
            progress_callback=update_progress,
        )
        job["status"] = "completed"
    except Exception as exc:
        job["error"] = str(exc)
        job["status"] = "failed"
    finally:
        try:
            os.remove(file_path)
        except OSError:
            pass
        job["completed_at"] = utc_now().isoformat()


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


def _validate_league_request(request: LeagueRequest) -> None:
    if not request.league_name.strip():
        raise HTTPException(status_code=400, detail="League name is required")
    if request.league_type not in {"snake", "auction"}:
        raise HTTPException(status_code=400, detail="league_type must be 'snake' or 'auction'")
    settings = request.settings
    if settings.ppr_type not in {"standard", "half_ppr", "ppr"}:
        raise HTTPException(status_code=400, detail="ppr_type must be standard, half_ppr, or ppr")
    integer_fields = [
        "num_teams",
        "roster_spots",
        "qb_slots",
        "rb_slots",
        "wr_slots",
        "te_slots",
        "flex_slots",
        "superflex_slots",
        "bench_spots",
        "taxi_spots",
    ]
    for field_name in integer_fields:
        value = getattr(settings, field_name)
        if value < 0:
            raise HTTPException(status_code=400, detail=f"{field_name} cannot be negative")
    if settings.num_teams < 2:
        raise HTTPException(status_code=400, detail="num_teams must be at least 2")
    for field_name in [
        "passing_td_points",
        "rushing_td_points",
        "receiving_td_points",
        "pass_yards_per_point",
        "rush_yards_per_point",
        "receiving_yards_per_point",
    ]:
        value = getattr(settings, field_name)
        if value <= 0:
            raise HTTPException(status_code=400, detail=f"{field_name} must be positive")


def _settings_to_dict(settings: LeagueSettings) -> Dict[str, Any]:
    return {
        "ppr_type": settings.ppr_type,
        "num_teams": settings.num_teams,
        "roster_spots": settings.roster_spots,
        "qb_slots": settings.qb_slots,
        "rb_slots": settings.rb_slots,
        "wr_slots": settings.wr_slots,
        "te_slots": settings.te_slots,
        "flex_slots": settings.flex_slots,
        "superflex_slots": settings.superflex_slots,
        "bench_spots": settings.bench_spots,
        "taxi_spots": settings.taxi_spots,
        "passing_td_points": settings.passing_td_points,
        "rushing_td_points": settings.rushing_td_points,
        "receiving_td_points": settings.receiving_td_points,
        "pass_yards_per_point": settings.pass_yards_per_point,
        "rush_yards_per_point": settings.rush_yards_per_point,
        "receiving_yards_per_point": settings.receiving_yards_per_point,
    }


def _league_to_response(league: League) -> LeagueResponse:
    return LeagueResponse(
        id=league.id,
        league_name=league.league_name,
        league_type=league.league_type,
        created_at=league.created_at.isoformat(),
        updated_at=league.updated_at.isoformat(),
        settings=_settings_to_dict(league.settings),
    )


def _apply_settings(settings: LeagueSettings, payload: LeagueSettingsPayload) -> None:
    for field_name, value in payload.model_dump().items():
        setattr(settings, field_name, value)


def _admin_default_league_settings(payload: AdminDefaultLeagueRequest) -> LeagueSettingsPayload:
    """Translate the admin helper's flat payload into the normal settings payload."""
    return LeagueSettingsPayload(
        ppr_type=payload.ppr_type,
        num_teams=payload.num_teams,
        roster_spots=payload.roster_spots,
        passing_td_points=payload.passing_td_points,
        rushing_td_points=payload.rushing_td_points,
        receiving_td_points=payload.receiving_td_points,
        pass_yards_per_point=payload.passing_yards_per_point,
        rush_yards_per_point=payload.rushing_yards_per_point,
        receiving_yards_per_point=payload.receiving_yards_per_point,
    )


def _get_owned_league(db: Session, league_id: int, user_id: int) -> League:
    league = db.query(League).filter(League.id == league_id, League.user_id == user_id).first()
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return league


def _latest_draft_market_season(db: Session) -> Optional[int]:
    row = db.query(DraftPlayerMarket.season).order_by(DraftPlayerMarket.season.desc()).first()
    return int(row[0]) if row else None


def _resolve_draft_pick_player(
    db: Session,
    player_name: str,
    season: int,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a live draft pick to canonical identity and market context when possible."""
    cleaned = player_name.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="player_name is required")

    resolution = resolve_to_canonical(cleaned, season, db=db)
    query = db.query(DraftPlayerMarket).filter(DraftPlayerMarket.season == season)
    if source:
        query = query.filter(DraftPlayerMarket.source == source)

    market = None
    canonical_player_id = None
    mapping_status = "needs_review"
    if resolution.get("ok"):
        canonical_player_id = resolution["canonical_player_id"]
        mapping_status = "mapped"
        market = query.filter(DraftPlayerMarket.canonical_player_id == canonical_player_id).first()
    else:
        market = query.filter(DraftPlayerMarket.source_player_name == cleaned).first()
        if market is not None:
            canonical_player_id = market.canonical_player_id
            mapping_status = "mapped"

    return {
        "source_player_name": market.source_player_name if market else cleaned,
        "position": market.position if market else None,
        "canonical_player_id": canonical_player_id,
        "mapping_status": mapping_status,
    }


def _round_for_pick(pick_number: int, settings: Optional[LeagueSettings]) -> int:
    num_teams = settings.num_teams if settings else 12
    return ((pick_number - 1) // max(1, int(num_teams or 12))) + 1


def _draft_pick_to_response(pick: LeagueDraftPick) -> DraftPickResponse:
    return DraftPickResponse(
        id=pick.id,
        league_id=pick.league_id,
        season=pick.season,
        round_num=pick.round_num or 0,
        pick_num=pick.pick_num or 0,
        fantasy_team_name=pick.fantasy_team_name,
        source_player_name=pick.source_player_name,
        position=pick.position,
        canonical_player_id=pick.canonical_player_id,
        mapping_status=pick.mapping_status,
        created_at=pick.created_at.isoformat(),
    )


def _upsert_draft_pick(
    db: Session,
    league: League,
    request: DraftPickRequest,
    default_team_name: str,
) -> LeagueDraftPick:
    if request.pick_number < 1:
        raise HTTPException(status_code=400, detail="pick_number must be positive")
    season = request.season or _latest_draft_market_season(db)
    if season is None:
        raise HTTPException(status_code=400, detail="No draft market data imported")

    resolved = _resolve_draft_pick_player(db, request.player_name, season, source=request.source)
    round_num = _round_for_pick(request.pick_number, league.settings)
    team_name = (request.team_name or default_team_name).strip() or default_team_name

    pick = (
        db.query(LeagueDraftPick)
        .filter(
            LeagueDraftPick.league_id == league.id,
            LeagueDraftPick.season == season,
            LeagueDraftPick.pick_num == request.pick_number,
        )
        .first()
    )
    if pick is None:
        pick = LeagueDraftPick(
            league_id=league.id,
            season=season,
            pick_num=request.pick_number,
            round_num=round_num,
        )
        db.add(pick)

    pick.round_num = round_num
    pick.fantasy_team_name = team_name
    pick.source_player_name = resolved["source_player_name"]
    pick.position = resolved["position"]
    pick.canonical_player_id = resolved["canonical_player_id"]
    pick.mapping_status = resolved["mapping_status"]
    return pick


def _upsert_my_roster_player(
    db: Session,
    league: League,
    pick: LeagueDraftPick,
    fantasy_team_name: str,
) -> None:
    roster_player = (
        db.query(LeagueRosterPlayer)
        .filter(
            LeagueRosterPlayer.league_id == league.id,
            LeagueRosterPlayer.season == pick.season,
            LeagueRosterPlayer.fantasy_team_name == fantasy_team_name,
            LeagueRosterPlayer.source_player_name == pick.source_player_name,
        )
        .first()
    )
    if roster_player is None:
        roster_player = LeagueRosterPlayer(
            league_id=league.id,
            season=pick.season,
            fantasy_team_name=fantasy_team_name,
            source_player_name=pick.source_player_name,
        )
        db.add(roster_player)
    roster_player.roster_slot = pick.position
    roster_player.position = pick.position
    roster_player.canonical_player_id = pick.canonical_player_id
    roster_player.mapping_status = pick.mapping_status


@app.get("/health")
def health_check():
    """Health check endpoint.

    Exposes the deployed commit so we can confirm exactly what Render is serving
    (Render sets RENDER_GIT_COMMIT at build/runtime; falls back to GIT_COMMIT).
    """
    commit = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "unknown"
    return {
        "ok": True,
        "status": "healthy",
        "service": "Superagent API",
        "commit": commit[:12] if commit != "unknown" else commit,
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


@app.get("/admin/draft-mappings")
def admin_draft_mappings(
    token: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    status: str = "pending",
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return low-confidence draft source mappings queued for admin review."""
    _require_admin_token(token)
    limit = max(1, min(limit, 500))
    skip = max(0, skip)

    query = db.query(DraftImportReview)
    if status:
        query = query.filter(DraftImportReview.status == status)
    reviews = (
        query.order_by(DraftImportReview.created_at.desc(), DraftImportReview.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    results = []
    for review in reviews:
        candidates = []
        if review.candidates:
            try:
                candidates = json.loads(review.candidates)
            except json.JSONDecodeError:
                candidates = []
        results.append(
            {
                "id": review.id,
                "source": review.source,
                "season": review.season,
                "source_player_name": review.source_player_name,
                "source_player_id": review.source_player_id,
                "status": review.status,
                "created_at": review.created_at.isoformat(),
                "resolved_at": review.resolved_at.isoformat() if review.resolved_at else None,
                "candidates": candidates,
            }
        )
    return results


@app.post("/admin/create-default-league")
def admin_create_default_league(
    request: AdminDefaultLeagueRequest,
    token: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Create a user-owned league from a flat admin payload."""
    _require_admin_token(token)
    email = _normalize_email(request.user_email)
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    league_request = LeagueRequest(
        league_name=request.league_name,
        league_type=request.league_type,
        settings=_admin_default_league_settings(request),
    )
    _validate_league_request(league_request)

    league = League(
        user_id=user.id,
        league_name=league_request.league_name.strip(),
        league_type=league_request.league_type,
    )
    db.add(league)
    db.flush()
    settings = LeagueSettings(league_id=league.id)
    _apply_settings(settings, league_request.settings)
    db.add(settings)
    db.commit()
    db.refresh(league)

    return {
        "ok": True,
        "league_id": league.id,
        "user_id": user.id,
        "settings_applied": league.settings is not None,
        "settings": _settings_to_dict(league.settings),
    }


@app.post("/admin/seed-canonical")
def admin_seed_canonical(
    background_tasks: BackgroundTasks,
    token: Optional[str] = None,
    season: Optional[int] = None,
    wait: bool = False,
    full_aliases: bool = False,
) -> Dict[str, Any]:
    """
    Seed canonical players from nflverse data without requiring production shell access.

    Render free instances do not provide shell access, so production operators can
    trigger the same deterministic seeding path through this protected endpoint.
    By default it runs as a background job and skips expensive weekly/play alias
    enrichment. Roster identity is enough for DraftSheets imports; set
    full_aliases=true later if you want the slower enrichment pass.
    """
    _require_admin_token(token)
    if season is not None and (season < 2020 or season > 2030):
        raise HTTPException(status_code=400, detail="Invalid season")

    seasons = [season] if season is not None else None
    if not wait:
        job_id = _create_admin_job(
            "seed_canonical",
            {
                "season": season,
                "seasons": seasons,
                "full_aliases": full_aliases,
            },
        )
        background_tasks.add_task(_run_seed_canonical_job, job_id, seasons, full_aliases)
        return {
            "ok": True,
            "job_id": job_id,
            "status": "queued",
            "status_url": f"/admin/jobs/{job_id}?token=YOUR_ADMIN_TOKEN",
        }

    try:
        summary = seed_canonical_players_from_nflverse(
            seasons=seasons,
            include_alias_enrichment=full_aliases,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Canonical seed failed: {exc}") from exc

    return {
        "ok": True,
        "season": season,
        "summary": summary,
    }


@app.get("/admin/jobs/{job_id}")
def admin_job_status(
    job_id: str,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """Return status for an in-memory admin background job."""
    _require_admin_token(token)
    job = ADMIN_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Admin job not found")
    return job


@app.post("/admin/draft-import")
async def admin_draft_import(
    background_tasks: BackgroundTasks,
    token: Optional[str] = None,
    source: str = "draftsheetsv6",
    season: int = 2025,
    sheet: Optional[str] = "DATA",
    wait: bool = False,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """
    Upload and import DraftSheets-style market data without production shell access.

    The uploaded file is written to a temporary path and then passed through the
    same strict importer used by the CLI, so validation and canonical mapping
    behavior stay identical across local and deployed environments. By default
    the import runs as a background job so Render Free requests do not hang.
    """
    _require_admin_token(token)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Upload filename is required")

    try:
        uploaded_name = Path(file.filename).name
        tmp_path = Path(tempfile.gettempdir()) / f"superagent-{uuid.uuid4()}-{uploaded_name}"
        tmp_path.write_bytes(await file.read())
        if not wait:
            job_id = _create_admin_job(
                "draft_import",
                {
                    "file_name": uploaded_name,
                    "source": source,
                    "season": season,
                    "sheet": sheet,
                },
            )
            background_tasks.add_task(
                _run_draft_import_job,
                job_id,
                str(tmp_path),
                source,
                season,
                sheet,
            )
            return {
                "ok": True,
                "job_id": job_id,
                "status": "queued",
                "status_url": f"/admin/jobs/{job_id}?token=YOUR_ADMIN_TOKEN",
            }

        try:
            summary = ingest_draft_market_file(
                file_path=str(tmp_path),
                source=source,
                season=season,
                sheet_name=sheet,
            )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return {
            "ok": True,
            "summary": summary,
        }
    except DraftIngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Draft import failed: {exc}") from exc


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


@app.post("/leagues", response_model=LeagueResponse)
def create_league(
    request: LeagueRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeagueResponse:
    """Create a user-owned fantasy league with scoring settings."""
    _validate_league_request(request)
    league = League(
        user_id=current_user.id,
        league_name=request.league_name.strip(),
        league_type=request.league_type,
    )
    db.add(league)
    db.flush()
    settings = LeagueSettings(league_id=league.id)
    _apply_settings(settings, request.settings)
    db.add(settings)
    db.commit()
    db.refresh(league)
    return _league_to_response(league)


@app.get("/leagues", response_model=List[LeagueResponse])
def list_leagues(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[LeagueResponse]:
    """List leagues owned by the current user."""
    leagues = (
        db.query(League)
        .filter(League.user_id == current_user.id)
        .order_by(League.updated_at.desc(), League.id.desc())
        .all()
    )
    return [_league_to_response(league) for league in leagues]


@app.get("/leagues/{league_id}", response_model=LeagueResponse)
def get_league(
    league_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeagueResponse:
    """Return one user-owned league configuration."""
    league = (
        db.query(League)
        .filter(League.id == league_id, League.user_id == current_user.id)
        .first()
    )
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")
    return _league_to_response(league)


@app.put("/leagues/{league_id}", response_model=LeagueResponse)
def update_league(
    league_id: int,
    request: LeagueRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeagueResponse:
    """Update a user-owned league and its scoring settings."""
    _validate_league_request(request)
    league = (
        db.query(League)
        .filter(League.id == league_id, League.user_id == current_user.id)
        .first()
    )
    if league is None:
        raise HTTPException(status_code=404, detail="League not found")

    league.league_name = request.league_name.strip()
    league.league_type = request.league_type
    league.updated_at = utc_now()
    if league.settings is None:
        league.settings = LeagueSettings(league_id=league.id)
    _apply_settings(league.settings, request.settings)
    db.commit()
    db.refresh(league)
    return _league_to_response(league)


@app.get("/leagues/{league_id}/draft/picks", response_model=DraftBoardResponse)
def list_draft_picks(
    league_id: int,
    season: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftBoardResponse:
    """List the recorded live draft board for a league."""
    _get_owned_league(db, league_id, current_user.id)
    season = season or _latest_draft_market_season(db)
    if season is None:
        raise HTTPException(status_code=400, detail="No draft market data imported")
    picks = (
        db.query(LeagueDraftPick)
        .filter(LeagueDraftPick.league_id == league_id, LeagueDraftPick.season == season)
        .order_by(LeagueDraftPick.pick_num.asc(), LeagueDraftPick.id.asc())
        .all()
    )
    return DraftBoardResponse(
        league_id=league_id,
        season=season,
        picks=[_draft_pick_to_response(pick).model_dump() for pick in picks],
    )


@app.post("/leagues/{league_id}/draft/picks", response_model=DraftPickResponse)
def record_draft_pick(
    league_id: int,
    request: DraftPickRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftPickResponse:
    """Record or update one pick made by any team in the live draft board."""
    league = _get_owned_league(db, league_id, current_user.id)
    pick = _upsert_draft_pick(db, league, request, default_team_name="Other")
    db.commit()
    db.refresh(pick)
    return _draft_pick_to_response(pick)


@app.post("/leagues/{league_id}/draft/my-pick", response_model=DraftPickResponse)
def record_my_pick(
    league_id: int,
    request: DraftPickRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftPickResponse:
    """Record one of the user's picks and add it to their stored roster."""
    league = _get_owned_league(db, league_id, current_user.id)
    team_name = (request.team_name or "My Team").strip() or "My Team"
    pick = _upsert_draft_pick(db, league, request, default_team_name=team_name)
    pick.fantasy_team_name = team_name
    _upsert_my_roster_player(db, league, pick, team_name)
    db.commit()
    db.refresh(pick)
    return _draft_pick_to_response(pick)


@app.post("/leagues/{league_id}/draft/picks/bulk", response_model=DraftBoardResponse)
def record_draft_picks_bulk(
    league_id: int,
    request: DraftBulkRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DraftBoardResponse:
    """Bulk-record a pasted draft board in one request.

    Resolves and upserts every pick (keyed by pick_num), routes the user's own
    picks ("is_mine") into the stored roster, and commits once at the end so a
    whole round saves in a single round-trip instead of one slow request per pick.
    """
    league = _get_owned_league(db, league_id, current_user.id)
    season = request.season or _latest_draft_market_season(db)
    if season is None:
        raise HTTPException(status_code=400, detail="No draft market data imported")

    recorded = 0
    updated = 0
    skipped = 0
    needs_review = 0
    needs_review_players: List[str] = []
    for item in request.picks:
        if not item.player_name or not item.player_name.strip() or item.pick_number < 1:
            skipped += 1
            continue
        existing = (
            db.query(LeagueDraftPick)
            .filter(
                LeagueDraftPick.league_id == league.id,
                LeagueDraftPick.season == season,
                LeagueDraftPick.pick_num == item.pick_number,
            )
            .first()
        )
        default_team = "My Team" if item.is_mine else "Other"
        pick_request = DraftPickRequest(
            pick_number=item.pick_number,
            player_name=item.player_name,
            team_name=item.team_name,
            season=season,
            source=request.source,
        )
        pick = _upsert_draft_pick(db, league, pick_request, default_team_name=default_team)
        if item.is_mine:
            team_name = (item.team_name or "My Team").strip() or "My Team"
            pick.fantasy_team_name = team_name
            _upsert_my_roster_player(db, league, pick, team_name)
        db.flush()
        if existing is not None:
            updated += 1
        else:
            recorded += 1
        if pick.mapping_status == "needs_review":
            needs_review += 1
            needs_review_players.append(pick.source_player_name)
    db.commit()

    picks = (
        db.query(LeagueDraftPick)
        .filter(LeagueDraftPick.league_id == league_id, LeagueDraftPick.season == season)
        .order_by(LeagueDraftPick.pick_num.asc(), LeagueDraftPick.id.asc())
        .all()
    )
    return DraftBoardResponse(
        league_id=league_id,
        season=season,
        picks=[_draft_pick_to_response(pick).model_dump() for pick in picks],
        summary={
            "recorded": recorded,
            "updated": updated,
            "skipped": skipped,
            "needs_review": needs_review,
            "needs_review_players": needs_review_players,
            "total_on_board": len(picks),
        },
    )


@app.delete("/leagues/{league_id}/draft/picks/last")
def undo_last_draft_pick(
    league_id: int,
    season: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Remove the most recently recorded pick for a league draft board."""
    _get_owned_league(db, league_id, current_user.id)
    season = season or _latest_draft_market_season(db)
    if season is None:
        raise HTTPException(status_code=400, detail="No draft market data imported")
    pick = (
        db.query(LeagueDraftPick)
        .filter(LeagueDraftPick.league_id == league_id, LeagueDraftPick.season == season)
        .order_by(LeagueDraftPick.pick_num.desc(), LeagueDraftPick.id.desc())
        .first()
    )
    if pick is None:
        return {"ok": True, "deleted": None}
    deleted = _draft_pick_to_response(pick).model_dump()
    if pick.fantasy_team_name:
        roster_player = (
            db.query(LeagueRosterPlayer)
            .filter(
                LeagueRosterPlayer.league_id == league_id,
                LeagueRosterPlayer.season == season,
                LeagueRosterPlayer.fantasy_team_name == pick.fantasy_team_name,
                LeagueRosterPlayer.source_player_name == pick.source_player_name,
            )
            .first()
        )
        if roster_player is not None:
            db.delete(roster_player)
    db.delete(pick)
    db.commit()
    return {"ok": True, "deleted": deleted}


@app.post("/integrations/espn/leagues")
def sync_espn_league(
    request: ESPNLeagueSyncRequest,
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """Fetch and persist ESPN league settings, rosters, and draft picks."""
    if request.season < 2020 or request.season > 2030:
        raise HTTPException(status_code=400, detail="Invalid ESPN season")
    try:
        return ingest_espn_league(
            espn_league_id=request.espn_league_id,
            season=request.season,
            user_id=current_user.id,
            espn_s2=request.espn_s2,
            swid=request.swid,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ESPN sync failed: {exc}") from exc


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
