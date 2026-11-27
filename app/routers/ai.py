"""Privacy-aware AI assistance, SSE, feedback and explicit tab binding."""

from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.core.ai.response import ManagedStreamingResponse
from app.core.auth import Principal, get_current_user
from app.schemas.ai import (
    AiStreamRequest,
    BindRequest,
    ProactiveSuggestRequest,
    SensitiveCheckRequest,
)
from app.schemas.feedback import AiFeedbackCreateRequest
from app.services import (
    ai_service,
    conversation_service,
    feedback_service,
    privacy_service,
)

router = APIRouter(prefix="/ai", tags=["AI Reading Assistant"])


@router.post("/check-sensitive")
async def check(
    data: SensitiveCheckRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Inspect text locally before provider transmission."""
    return await privacy_service.check_sensitive(current, data.text)


@router.post("/stream", response_class=StreamingResponse)
async def stream(
    data: AiStreamRequest, current: Principal = Depends(get_current_user)
) -> StreamingResponse:
    """Stream one isolated AI operation after admission/policy checks."""
    prepared = await ai_service.prepare(current, data)
    return ManagedStreamingResponse(
        ai_service.generate(current, prepared),
        cleanup=prepared.lease.close,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/proactive-suggest")
async def proactive(
    data: ProactiveSuggestRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Offer an optional hint respecting opt-out and sensitivity."""
    return await ai_service.proactive(current, data)


@router.post("/feedback", status_code=201)
async def feedback(
    data: AiFeedbackCreateRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Upsert a voluntary rating on an owned message."""
    return await feedback_service.submit(current, data)


@router.post("/conversations/{id}/bind")
async def bind(
    id: UUID, data: BindRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Explicitly move a conversation to an active reading session."""
    return await conversation_service.bind(current, id, data)
