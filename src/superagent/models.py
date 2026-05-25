"""
SQLAlchemy models for Superagent product-layer persistence.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


def utc_now() -> datetime:
    """Return a timezone-naive UTC timestamp for database portability."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def default_session_expiry() -> datetime:
    """Default conversation session expiry."""
    return utc_now() + timedelta(days=30)


class User(Base):
    """Authenticated Superagent user."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    last_active = Column(DateTime, default=utc_now, nullable=False)

    sessions = relationship(
        "ConversationSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    leagues = relationship(
        "League",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    rate_limits = relationship(
        "RateLimit",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class ConversationSession(Base):
    """Persistent conversation session."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, default=default_session_expiry, nullable=False)
    last_active = Column(DateTime, default=utc_now, nullable=False)

    user = relationship("User", back_populates="sessions")
    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """Persisted user or assistant message."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(
        String,
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    tools_used = Column(Text)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    session = relationship("ConversationSession", back_populates="messages")


class RateLimit(Base):
    """Per-user hourly request counter."""

    __tablename__ = "rate_limits"
    __table_args__ = (UniqueConstraint("user_id", "hour", name="uq_rate_limit_user_hour"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    hour = Column(DateTime, nullable=False)
    request_count = Column(Integer, default=1, nullable=False)

    user = relationship("User", back_populates="rate_limits")


class CanonicalPlayer(Base):
    """Person-level player identity used across internal and external sources."""

    __tablename__ = "canonical_players"

    canonical_player_id = Column(String, primary_key=True)
    nflverse_player_id = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, nullable=False)
    normalized_name = Column(String, nullable=False, index=True)
    birth_date = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    seasons = relationship(
        "PlayerSeason",
        back_populates="canonical_player",
        cascade="all, delete-orphan",
    )
    aliases = relationship(
        "CanonicalPlayerAlias",
        back_populates="canonical_player",
        cascade="all, delete-orphan",
    )
    external_mappings = relationship(
        "ExternalPlayerMapping",
        back_populates="canonical_player",
    )


class PlayerSeason(Base):
    """Season-scoped team, position, and context for a canonical player."""

    __tablename__ = "player_seasons"
    __table_args__ = (
        UniqueConstraint(
            "canonical_player_id",
            "season",
            "team",
            "position",
            name="uq_player_season_context",
        ),
    )

    id = Column(Integer, primary_key=True)
    canonical_player_id = Column(
        String,
        ForeignKey("canonical_players.canonical_player_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season = Column(Integer, nullable=False, index=True)
    team = Column(String, nullable=True)
    position = Column(String, nullable=True, index=True)
    age = Column(Integer, nullable=True)
    status = Column(String, default="active", nullable=False)

    canonical_player = relationship("CanonicalPlayer", back_populates="seasons")


class CanonicalPlayerAlias(Base):
    """Known player name variation from nflverse or an external source."""

    __tablename__ = "canonical_player_aliases"
    __table_args__ = (
        UniqueConstraint(
            "canonical_player_id",
            "normalized_alias",
            "source",
            name="uq_player_alias_source",
        ),
    )

    id = Column(Integer, primary_key=True)
    canonical_player_id = Column(
        String,
        ForeignKey("canonical_players.canonical_player_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias = Column(String, nullable=False)
    normalized_alias = Column(String, nullable=False, index=True)
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    canonical_player = relationship("CanonicalPlayer", back_populates="aliases")


class ExternalPlayerMapping(Base):
    """Mapping from a season-specific external source row to a canonical player."""

    __tablename__ = "external_player_mappings"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "season",
            "source_player_name",
            "source_player_id",
            name="uq_external_player_mapping",
        ),
    )

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    source_player_name = Column(String, nullable=False)
    source_player_id = Column(String, nullable=True)
    canonical_player_id = Column(
        String,
        ForeignKey("canonical_players.canonical_player_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence = Column(Float, default=0.0, nullable=False)
    status = Column(String, default="needs_review", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    canonical_player = relationship("CanonicalPlayer", back_populates="external_mappings")


class DraftImportReview(Base):
    """Low-confidence external player mapping queued for operator review."""

    __tablename__ = "draft_import_review"

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    source_player_name = Column(String, nullable=False)
    source_player_id = Column(String, nullable=True)
    candidates = Column(Text, nullable=True)
    status = Column(String, default="pending", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class DraftMarketImport(Base):
    """A strict draft market data import batch."""

    __tablename__ = "draft_market_imports"
    __table_args__ = (
        UniqueConstraint("source", "season", "file_name", name="uq_draft_market_import_file"),
    )

    id = Column(Integer, primary_key=True)
    source = Column(String, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    file_name = Column(String, nullable=False)
    sheet_name = Column(String, nullable=True)
    status = Column(String, default="completed", nullable=False)
    rows_seen = Column(Integer, default=0, nullable=False)
    rows_imported = Column(Integer, default=0, nullable=False)
    rows_needing_review = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    player_markets = relationship(
        "DraftPlayerMarket",
        back_populates="import_batch",
        cascade="all, delete-orphan",
    )


class DraftPlayerMarket(Base):
    """Seasonal draft market row for one canonical player from one imported source."""

    __tablename__ = "draft_player_markets"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "season",
            "canonical_player_id",
            name="uq_draft_player_market_source_season_player",
        ),
    )

    id = Column(Integer, primary_key=True)
    import_id = Column(
        Integer,
        ForeignKey("draft_market_imports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source = Column(String, nullable=False, index=True)
    season = Column(Integer, nullable=False, index=True)
    canonical_player_id = Column(
        String,
        ForeignKey("canonical_players.canonical_player_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_player_name = Column(String, nullable=False)
    team = Column(String, nullable=True)
    position = Column(String, nullable=True, index=True)
    position_rank = Column(Integer, nullable=True)
    bye_week = Column(Integer, nullable=True)
    overall_rank = Column(Float, nullable=True)
    adp = Column(Float, nullable=True)
    ecr = Column(Float, nullable=True)
    avg_rank = Column(Float, nullable=True)
    best_rank = Column(Float, nullable=True)
    worst_rank = Column(Float, nullable=True)
    std_dev = Column(Float, nullable=True)
    ecr_vs_adp = Column(Float, nullable=True)
    floor = Column(Float, nullable=True)
    ceiling = Column(Float, nullable=True)
    value = Column(Float, nullable=True)
    injury_risk = Column(String, nullable=True)
    raw_data = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    import_batch = relationship("DraftMarketImport", back_populates="player_markets")
    canonical_player = relationship("CanonicalPlayer")
    source_ranks = relationship(
        "DraftSourceRank",
        back_populates="player_market",
        cascade="all, delete-orphan",
    )


class DraftSourceRank(Base):
    """Per-provider rank attached to a draft market player row."""

    __tablename__ = "draft_source_ranks"
    __table_args__ = (
        UniqueConstraint("market_id", "rank_source", name="uq_draft_source_rank_market"),
    )

    id = Column(Integer, primary_key=True)
    market_id = Column(
        Integer,
        ForeignKey("draft_player_markets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rank_source = Column(String, nullable=False, index=True)
    rank_value = Column(Float, nullable=False)

    player_market = relationship("DraftPlayerMarket", back_populates="source_ranks")


class League(Base):
    """User-owned fantasy league configuration container."""

    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    league_name = Column(String, nullable=False)
    league_type = Column(String, default="snake", nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    user = relationship("User", back_populates="leagues")
    settings = relationship(
        "LeagueSettings",
        back_populates="league",
        cascade="all, delete-orphan",
        uselist=False,
    )


class LeagueSettings(Base):
    """Fantasy scoring and roster settings for one league."""

    __tablename__ = "league_settings"

    id = Column(Integer, primary_key=True)
    league_id = Column(
        Integer,
        ForeignKey("leagues.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    ppr_type = Column(String, default="ppr", nullable=False)
    num_teams = Column(Integer, default=12, nullable=False)
    roster_spots = Column(Integer, default=16, nullable=False)
    qb_slots = Column(Integer, default=1, nullable=False)
    rb_slots = Column(Integer, default=2, nullable=False)
    wr_slots = Column(Integer, default=2, nullable=False)
    te_slots = Column(Integer, default=1, nullable=False)
    flex_slots = Column(Integer, default=1, nullable=False)
    superflex_slots = Column(Integer, default=0, nullable=False)
    bench_spots = Column(Integer, default=6, nullable=False)
    taxi_spots = Column(Integer, default=0, nullable=False)
    passing_td_points = Column(Float, default=4.0, nullable=False)
    rushing_td_points = Column(Float, default=6.0, nullable=False)
    receiving_td_points = Column(Float, default=6.0, nullable=False)
    pass_yards_per_point = Column(Float, default=25.0, nullable=False)
    rush_yards_per_point = Column(Float, default=10.0, nullable=False)
    receiving_yards_per_point = Column(Float, default=10.0, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    league = relationship("League", back_populates="settings")
