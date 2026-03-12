"""Chat session and message routes."""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import get_db
from backend.db.models import User, ChatSession, Message
from backend.db.schemas import (
    SessionCreate, SessionRename, SessionRead,
    MessageCreate, MessageRead,
)
from backend.db.auth import get_current_user

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.get("", response_model=List[SessionRead])
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.asc())
    )
    return [SessionRead.model_validate(s) for s in result.scalars().all()]


@router.post("", response_model=SessionRead)
async def create_session(
    data: SessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ChatSession(
        user_id=current_user.id,
        title=data.title,
        mode=data.mode,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return SessionRead.model_validate(session)


@router.patch("/{session_id}", response_model=SessionRead)
async def rename_session(
    session_id: str,
    data: SessionRename,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    session.title = data.title
    await db.flush()
    await db.refresh(session)
    return SessionRead.model_validate(session)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    await db.delete(session)
    return {"detail": "Đã xóa session"}


@router.get("/{session_id}/messages", response_model=List[MessageRead])
async def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return [MessageRead.model_validate(m) for m in result.scalars().all()]


@router.post("/{session_id}/messages", response_model=MessageRead)
async def add_message(
    session_id: str,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session không tồn tại")

    msg = Message(
        session_id=session_id,
        role=data.role,
        content=data.content,
        route_type=data.route_type,
    )
    db.add(msg)

    # Auto-rename session on first user message
    if data.role == "user" and session.title == "Đoạn chat mới":
        session.title = data.content[:30] + ("..." if len(data.content) > 30 else "")

    await db.flush()
    await db.refresh(msg)
    return MessageRead.model_validate(msg)
