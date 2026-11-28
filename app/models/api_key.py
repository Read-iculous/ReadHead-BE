"""Encrypted user-owned provider keys."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Created, Identity, Updated


class UserApiKey(Identity, Created, Updated, Base):
    """At most one stored key per user and provider."""

    __tablename__ = "user_api_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "provider"),
        CheckConstraint("provider IN ('openai','gemini','claude')"),
        Index("idx_user_api_keys_active", "user_id", "provider", "is_active"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    encrypted_key: Mapped[str] = mapped_column(Text)
    key_hint: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
