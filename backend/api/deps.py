"""
Shared dependencies and helpers for API routes.
"""
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.database import async_session_factory
from backend.db.models import Message

logger = logging.getLogger(__name__)


async def load_history(session_id: Optional[str], limit: int = 5) -> list:
    """Load last N messages from a session for conversation context."""
    if not session_id:
        return []
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            messages = result.scalars().all()
            return [
                {"role": m.role, "content": m.content}
                for m in reversed(messages)
            ]
    except Exception as e:
        logger.warning("Failed to load history for session %s: %s", session_id, e)
        return []
