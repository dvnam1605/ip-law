import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.models import User, BlacklistedToken

# ── Config ───────────────────────────────────────────

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-secret-key-in-production")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24h default

# ── Password Hashing (using bcrypt directly) ────────


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


# ── JWT Token ────────────────────────────────────────

security = HTTPBearer(auto_error=False)


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# ── FastAPI Dependencies ─────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate user from JWT Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không được cung cấp",
        )

    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
        )

    # Check if token is blacklisted
    result = await db.execute(
        select(BlacklistedToken).where(BlacklistedToken.token == token)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token đã bị thu hồi, vui lòng đăng nhập lại",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ",
        )

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Người dùng không tồn tại",
        )

    return user


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Like get_current_user but returns None instead of raising."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def blacklist_token(token: str, db: AsyncSession) -> None:
    """Add a token to the blacklist."""
    payload = decode_token(token)
    if payload is None:
        return  # Token already invalid, no need to blacklist

    exp_timestamp = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else datetime.now(timezone.utc)

    # Check if already blacklisted
    result = await db.execute(
        select(BlacklistedToken).where(BlacklistedToken.token == token)
    )
    if result.scalar_one_or_none():
        return  # Already blacklisted

    entry = BlacklistedToken(
        token=token,
        expires_at=expires_at,
    )
    db.add(entry)


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """Remove blacklisted tokens that have already expired (JWT rejects them anyway)."""
    from sqlalchemy import delete as sa_delete
    now = datetime.now(timezone.utc)
    result = await db.execute(
        sa_delete(BlacklistedToken).where(BlacklistedToken.expires_at < now)
    )
    await db.commit()
    return result.rowcount
