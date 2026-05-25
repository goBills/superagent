"""
Per-user rate limiting for Superagent.
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from superagent.config import RATE_LIMIT_PER_HOUR
from superagent.models import RateLimit


def current_hour() -> datetime:
    """Return the current UTC hour bucket."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return now.replace(minute=0, second=0, microsecond=0)


def check_rate_limit(user_id: int, db: Session) -> bool:
    """
    Increment and check a user's hourly request quota.

    Returns True when the request is allowed and False when the user has already
    reached the configured hourly quota.
    """
    hour_start = current_hour()
    rate_limit = (
        db.query(RateLimit)
        .filter(RateLimit.user_id == user_id, RateLimit.hour == hour_start)
        .first()
    )

    if rate_limit is None:
        db.add(RateLimit(user_id=user_id, hour=hour_start, request_count=1))
        db.commit()
        return True

    if rate_limit.request_count >= RATE_LIMIT_PER_HOUR:
        return False

    rate_limit.request_count += 1
    db.commit()
    return True
