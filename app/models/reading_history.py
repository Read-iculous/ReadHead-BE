"""Reading logs suppressed by privacy policy."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Identity


class ReadingHistory(Identity, Base):
    """One recorded page visit."""

    __tablename__ = "reading_history"
    __table_args__ = (
        Index("idx_reading_history_user_visited", "user_id", "visited_at"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    page_url: Mapped[str] = mapped_column(Text)
    page_title: Mapped[str | None] = mapped_column(String(500))
    cached_summary: Mapped[str | None] = mapped_column(Text)
    reading_time_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    is_bookmarked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
