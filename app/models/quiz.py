"""Persistent comprehension questions and a single graded attempt."""

from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Created, Identity


class QuizRecord(Identity, Created, Base):
    """Server-only answer keys; never returned before submission."""

    __tablename__ = "quiz_records"
    __table_args__ = (Index("idx_quiz_records_user_created", "user_id", "created_at"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    page_url: Mapped[str] = mapped_column(Text)
    questions_payload: Mapped[list] = mapped_column(JSONB)
    user_answers: Mapped[dict | None] = mapped_column(JSONB)
    score: Mapped[int | None] = mapped_column(Integer)
