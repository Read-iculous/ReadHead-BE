"""User accounts and linked OAuth identities."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Created, Identity, Updated


class User(Identity, Created, Updated, Base):
    """Core account registry with a serialized sync clock."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user','admin')"),
        CheckConstraint("status IN ('active','suspended','banned')"),
        CheckConstraint("is_active = (status = 'active')"),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(150))
    avatar_url: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="user", server_default="user")
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    sync_clock: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OAuthAccount(Identity, Created, Base):
    """Verified provider identity associated with an account."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(50))
    provider_user_id: Mapped[str] = mapped_column(String(255))
