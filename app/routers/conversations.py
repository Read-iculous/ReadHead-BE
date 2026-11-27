"""Owned conversation and chronological message history routes."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.auth import Principal, get_current_user
from app.schemas.common import PostgresText
from app.schemas.responses import (
    ConversationResponse,
    Envelope,
    MessageResponse,
    PageData,
)
from app.services import conversation_service

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.get(
    "",
    response_model=Envelope[PageData[ConversationResponse]],
    response_model_exclude_none=False,
)
async def conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: PostgresText | None = Query(None, max_length=255),
    current: Principal = Depends(get_current_user),
) -> dict:
    """List and search recent live conversations."""
    return await conversation_service.list_conversations(
        current, page, page_size, search
    )


@router.get(
    "/{id}/messages",
    response_model=Envelope[PageData[MessageResponse]],
    response_model_exclude_none=False,
)
async def messages(
    id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    order: Literal["asc", "desc"] = "asc",
    current: Principal = Depends(get_current_user),
) -> dict:
    """Read immutable turns without fetching the source page."""
    return await conversation_service.messages(current, id, page, page_size, order)


@router.delete("/{id}", status_code=204)
async def remove(id: UUID, current: Principal = Depends(get_current_user)) -> Response:
    """Soft delete a conversation and hide its messages."""
    await conversation_service.delete_conversation(current, id)
    return Response(status_code=204)
