"""Revocable login sessions, distinct from browser reading sessions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Created, Identity


class AuthSession(Identity, Created, Base):
    """One login session owning a complete refresh-token chain."""

    __tablename__ = "auth_sessions"
    __table_args__ = (
        UniqueConstraint("id", "user_id"),
        CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND revocation_reason IN ('logout','security'))"
        ),
        Index("idx_auth_sessions_user", "user_id", "revoked_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    device_info: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason: Mapped[str | None] = mapped_column(String(20))
