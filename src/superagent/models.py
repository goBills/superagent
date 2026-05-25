"""
SQLAlchemy models for Superagent product-layer persistence.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
