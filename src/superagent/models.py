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
