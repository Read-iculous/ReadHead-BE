"""User ratings linked to owned assistant messages."""

from uuid import UUID

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Created, Identity, Updated


class AiFeedback(Identity, Created, Updated, Base):
    """One atomically replaceable rating per user/message."""

    __tablename__ = "ai_feedback"
    __table_args__ = (UniqueConstraint("user_id", "message_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    message_id: Mapped[UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE")
    )
    rating: Mapped[str] = mapped_column(String(10))
    report_reason: Mapped[str | None] = mapped_column(String(50))
    comment: Mapped[str | None] = mapped_column(Text)
