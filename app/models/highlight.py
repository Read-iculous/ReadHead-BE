"""Saved text selections and user notes."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Created, Identity, Updated


class Highlight(Identity, Created, Updated, Base):
    """Versioned, user-owned highlight."""

    __tablename__ = "highlights"
    __table_args__ = (
        Index("idx_highlights_user_url", "user_id", func.md5(text("page_url"))),
        Index("idx_highlights_sync", "user_id", "updated_at", "id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    page_url: Mapped[str] = mapped_column(Text)
    highlighted_text: Mapped[str] = mapped_column(Text)
    user_note: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(
        String(20), default="yellow", server_default="yellow"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
