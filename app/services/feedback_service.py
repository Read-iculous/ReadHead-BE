"""Ownership-checked, atomic voluntary feedback updates."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.security import utcnow
from app.models.conversation import Conversation, Message
from app.models.feedback import AiFeedback
from app.schemas.common import public
from app.schemas.feedback import AiFeedbackCreateRequest


async def submit(principal: Principal, data: AiFeedbackCreateRequest) -> dict:
    """Upsert one rating only for an owned, live assistant message."""
    async with transaction() as db:
        row = await db.scalar(
            select(Message)
            .join(Conversation)
            .where(
                Message.id == data.message_id,
                Conversation.user_id == principal.user_id,
                Conversation.is_deleted.is_(False),
                Message.sender_role == "assistant",
            )
        )
        if not row:
            raise AppException(404, "MESSAGE_NOT_FOUND", "Assistant message not found")
        values = data.model_dump()
        result = await db.execute(
            insert(AiFeedback)
            .values(user_id=principal.user_id, **values)
            .on_conflict_do_update(
                index_elements=["user_id", "message_id"],
                set_=dict(
                    rating=data.rating,
                    report_reason=data.report_reason,
                    comment=data.comment,
                    updated_at=utcnow(),
                ),
            )
            .returning(AiFeedback)
        )
        return {
            "data": public(
                result.scalar_one(),
                (
                    "id",
                    "message_id",
                    "rating",
                    "report_reason",
                    "comment",
                    "created_at",
                    "updated_at",
                ),
            )
        }
