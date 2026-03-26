"""Admin dashboard endpoints."""
import random
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.db.database import get_db
from backend.db.models import User, ChatSession, Trademark
from backend.db.auth import get_current_admin_user

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/stats")
async def get_admin_stats(
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_users_result = await db.execute(select(func.count(User.id)))
    total_users = total_users_result.scalar() or 0

    total_trademarks_result = await db.execute(select(func.count(Trademark.id)))
    total_trademarks = total_trademarks_result.scalar() or 0

    total_sessions_result = await db.execute(select(func.count(ChatSession.id)))
    total_sessions = total_sessions_result.scalar() or 0

    # Mock count cho bộ luật và án lệ từ Neo4j
    total_laws = 1420
    total_precedents = 70

    today = datetime.now()
    visits_data = []
    users_data = []

    for i in range(6, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        visits_data.append({"date": d, "visits": random.randint(10, 50)})
        users_data.append({"date": d, "new_users": random.randint(1, 5)})

    return {
        "success": True,
        "totals": {
            "users": total_users,
            "trademarks": total_trademarks,
            "visits": total_sessions,
            "laws": total_laws,
            "precedents": total_precedents,
        },
        "charts": {
            "visits_over_time": visits_data,
            "users_over_time": users_data,
        }
    }


@router.get("/users")
async def get_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(select(func.count(User.id)))
    total = total_result.scalar() or 0

    stmt = select(User).order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    users = result.scalars().all()

    return {
        "success": True,
        "total": total,
        "data": [
            {
                "id": u.id,
                "username": u.username,
                "is_admin": u.is_admin,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }


@router.get("/sessions")
async def get_admin_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_admin: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_result = await db.execute(select(func.count(ChatSession.id)))
    total = total_result.scalar() or 0

    stmt = (select(ChatSession)
            .options(selectinload(ChatSession.user))
            .order_by(ChatSession.created_at.desc())
            .offset(skip)
            .limit(limit))
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return {
        "success": True,
        "total": total,
        "data": [
            {
                "id": s.id,
                "title": s.title,
                "mode": s.mode,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "username": s.user.username if s.user else "Unknown"
            }
            for s in sessions
        ]
    }
