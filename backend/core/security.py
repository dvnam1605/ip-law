"""Security utilities for JWT and password hashing."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from backend.core.config import config

MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when password exceeds bcrypt's byte limit."""


def _check_password_length(password: str) -> None:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password too long. Maximum {MAX_PASSWORD_BYTES} bytes allowed, "
            f"got {len(password_bytes)} bytes."
        )


def hash_password(password: str) -> str:
    _check_password_length(password)
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        _check_password_length(plain_password)
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (PasswordTooLongError, ValueError):
        return False


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.JWT_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    try:
        return jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
        )
    except JWTError:
        return None
