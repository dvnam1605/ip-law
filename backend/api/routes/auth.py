"""Authentication routes."""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import User
from backend.db.schemas import (
    UserCreate, UserLogin, TokenResponse, UserRead,
    UsernameChange, PasswordChange,
)
from backend.db.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, blacklist_token,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")

    user = User(
        username=data.username,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    token = create_access_token(user.id, user.username)
    return TokenResponse(
        access_token=token,
        user=UserRead.model_validate(user),
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user)


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    db: AsyncSession = Depends(get_db),
):
    """Blacklist the current token so it can no longer be used."""
    await blacklist_token(credentials.credentials, db)
    return {"detail": "Đã đăng xuất thành công"}


@router.patch("/username", response_model=UserRead)
async def change_username(
    data: UsernameChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == data.new_username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")

    current_user.username = data.new_username
    await db.flush()
    await db.refresh(current_user)
    return UserRead.model_validate(current_user)


@router.patch("/password")
async def change_password(
    data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    current_user.hashed_password = hash_password(data.new_password)
    await db.flush()
    return {"detail": "Đổi mật khẩu thành công"}
