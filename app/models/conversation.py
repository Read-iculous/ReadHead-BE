"""Tab-bound conversations and immutable source-grounded turns."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Created, Identity, Updated


class Conversation(Identity, Created, Updated, Base):
    """Versioned conversation with a sync tombstone."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("idx_conversations_user_updated", "user_id", "is_deleted", "updated_at"),
        Index("idx_conversations_sync", "user_id", "updated_at", "id"),
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reading_session_id: Mapped[UUID | None]
    title: Mapped[str] = mapped_column(
        String(255), default="New Conversation", server_default="New Conversation"
    )
    page_url: Mapped[str | None] = mapped_column(Text)
    page_title: Mapped[str | None] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", passive_deletes=True, lazy="raise"
    )


class Message(Identity, Created, Base):
    """Immutable user or assistant turn with attribution metadata."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_messages_conversation_created", "conversation_id", "created_at"),
    )
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    sender_role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    selected_context: Mapped[str | None] = mapped_column(Text)
    provider_used: Mapped[str | None] = mapped_column(String(50))
    model_used: Mapped[str | None] = mapped_column(String(100))
    is_grounded: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    uncertainty_flag: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    grounding_notes: Mapped[str | None] = mapped_column(Text)
    conversation: Mapped[Conversation] = relationship(
        back_populates="messages", lazy="raise"
    )
