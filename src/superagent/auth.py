"""
Authentication helpers for Superagent.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from superagent.config import SECRET_KEY, TOKEN_EXPIRY_DAYS


ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a bcrypt hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    """Create a signed JWT for a user."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_DAYS)
    payload = {
        "user_id": user_id,
        "exp": expires_at,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[int]:
    """Verify a JWT and return the user id when valid."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None

    user_id = payload.get("user_id")
    if isinstance(user_id, int):
        return user_id
    return None
