import sqlalchemy
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime, Integer, Float, Index, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ARRAY
from db.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    is_admin: Mapped[bool] = mapped_column(sqlalchemy.Boolean, default=False, server_default=sqlalchemy.text('false'))

    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), default="Đoạn chat mới")
    mode: Mapped[str] = mapped_column(String(20), default="smart")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id: Mapped[str] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # 'user' or 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    route_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class BlacklistedToken(Base):
    __tablename__ = "blacklisted_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(500), unique=True, nullable=False, index=True)
    blacklisted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# ── Trademark ────────────────────────────────────────

# Many-to-many: Trademark ↔ NiceClass
trademark_nice_class = Table(
    "trademark_nice_class",
    Base.metadata,
    Column("trademark_id", Integer, ForeignKey("trademarks.id", ondelete="CASCADE"), primary_key=True),
    Column("nice_class_id", Integer, ForeignKey("nice_classes.id", ondelete="CASCADE"), primary_key=True),
)


class Trademark(Base):
    __tablename__ = "trademarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_name: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    brand_name_lower: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    st13: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True, index=True)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    application_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status_date: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_office: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    feature: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ipr_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    country_of_filing: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registration_date: Mapped[str | None] = mapped_column(String(100), nullable=True)
    application_date: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[str | None] = mapped_column(String(100), nullable=True)
    crawled_at: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Owner (inline for simplicity — most records have 1 owner)
    owner_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    owner_country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    nice_classes: Mapped[list["NiceClass"]] = relationship(
        secondary=trademark_nice_class, back_populates="trademarks", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_trademarks_brand_name_trgm", "brand_name_lower", postgresql_using="gin",
              postgresql_ops={"brand_name_lower": "gin_trgm_ops"}),
    )


class NiceClass(Base):
    __tablename__ = "nice_classes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    class_number: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)

    trademarks: Mapped[list["Trademark"]] = relationship(
        secondary=trademark_nice_class, back_populates="nice_classes", lazy="selectin"
    )
