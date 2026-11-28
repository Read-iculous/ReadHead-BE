"""Owned reading conversations, tab bindings and immutable messages."""

from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import select

from app.core import redis
from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.models.conversation import Conversation, Message
from app.schemas.ai import BindRequest
from app.services.common import (
    CONVERSATION_FIELDS,
    MESSAGE_FIELDS,
    owned,
    paginate,
    sync_stamp,
)


async def list_conversations(
    principal: Principal, page: int, page_size: int, search: str | None
) -> dict:
    """List recent conversations without refetching historical page URLs."""
    async with transaction() as db:
        q = select(Conversation).where(
            Conversation.user_id == principal.user_id,
            Conversation.is_deleted.is_(False),
        )
        if search:
            q = q.where(Conversation.title.icontains(search, autoescape=True))
        return await paginate(
            db,
            q.order_by(Conversation.updated_at.desc(), Conversation.id),
            CONVERSATION_FIELDS,
            page,
            page_size,
        )


async def messages(
    principal: Principal, cid: UUID, page: int, page_size: int, order: str
) -> dict:
    """Hide messages of deleted or unowned conversations."""
    async with transaction() as db:
        await owned(db, Conversation, cid, principal.user_id, "CONVERSATION_NOT_FOUND")
        q = select(Message).where(Message.conversation_id == cid)
        columns = (
            (Message.created_at.asc(), Message.id.asc())
            if order == "asc"
            else (Message.created_at.desc(), Message.id.desc())
        )
        return await paginate(db, q.order_by(*columns), MESSAGE_FIELDS, page, page_size)


async def delete_conversation(principal: Principal, cid: UUID) -> None:
    """Soft delete and retain the tombstone for cross-device sync."""
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        row = await owned(
            db, Conversation, cid, principal.user_id, "CONVERSATION_NOT_FOUND", True
        )
        row.is_deleted = True
        row.version += 1
        row.updated_at = stamp


async def bind(principal: Principal, cid: UUID, data: BindRequest) -> dict:
    """Explicitly transfer ownership of the active tab context."""
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        row = await owned(
            db, Conversation, cid, principal.user_id, "CONVERSATION_NOT_FOUND", True
        )
        try:
            if await redis.client.exists(
                f"conversation_stream:{principal.user_id}:{cid}"
            ):
                raise AppException(
                    409, "CONVERSATION_BUSY", "Conversation is currently streaming"
                )
        except RedisError:
            raise AppException(
                503,
                "SERVICE_DEGRADED",
                "Tab rebinding is unavailable while stream coordination is offline",
            ) from None
        if row.page_url and row.page_url != data.page_url:
            raise AppException(
                400,
                "TAB_CONTEXT_MISMATCH",
                "Reading page does not match this conversation",
            )
        row.reading_session_id = data.reading_session_id
        row.version += 1
        row.updated_at = stamp
        return {
            "data": dict(
                conversation_id=cid,
                reading_session_id=data.reading_session_id,
                is_bound=True,
            )
        }
