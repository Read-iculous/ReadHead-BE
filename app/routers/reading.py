"""Reading history and explicit highlight storage routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from app.core.auth import Principal, get_current_user
from app.schemas.common import PostgresText
from app.schemas.reading import HighlightCreate, ReadingHistoryCreate
from app.schemas.responses import (
    Envelope,
    HighlightResponse,
    PageData,
    ReadingHistoryResponse,
)
from app.services import reading_service

router = APIRouter(prefix="/reading", tags=["Reading Data"])


@router.post(
    "/history",
    status_code=201,
    response_model=Envelope[ReadingHistoryResponse | None],
    response_model_exclude_none=False,
)
async def record(
    data: ReadingHistoryCreate,
    response: Response,
    current: Principal = Depends(get_current_user),
) -> dict:
    """Record a visit, or return 200/null when privacy policy skips logging."""
    result = await reading_service.record_history(current, data)
    response.status_code = 201 if result["data"] is not None else 200
    return result


@router.get(
    "/history",
    response_model=Envelope[PageData[ReadingHistoryResponse]],
    response_model_exclude_none=False,
)
async def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: PostgresText | None = Query(None, max_length=255),
    current: Principal = Depends(get_current_user),
) -> dict:
    """Read paginated visit logs."""
    return await reading_service.list_history(current, page, page_size, search)


@router.delete("/history", status_code=204)
async def clear(current: Principal = Depends(get_current_user)) -> Response:
    """Clear visits and synchronize conversation URL anonymization."""
    await reading_service.clear_history(current)
    return Response(status_code=204)


@router.post(
    "/highlights",
    status_code=201,
    response_model=Envelope[HighlightResponse],
    response_model_exclude_none=False,
)
async def save(
    data: HighlightCreate, current: Principal = Depends(get_current_user)
) -> dict:
    """Save an explicit highlight and optional note."""
    return await reading_service.create_highlight(current, data)


@router.get(
    "/highlights",
    response_model=Envelope[PageData[HighlightResponse]],
    response_model_exclude_none=False,
)
async def highlights(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    page_url: PostgresText | None = Query(None, max_length=8192),
    current: Principal = Depends(get_current_user),
) -> dict:
    """List saved selections, optionally filtered by source URL."""
    return await reading_service.list_highlights(current, page, page_size, page_url)


@router.delete("/highlights/{id}", status_code=204)
async def remove(id: UUID, current: Principal = Depends(get_current_user)) -> Response:
    """Create a highlight tombstone for cross-device deletion."""
    await reading_service.delete_highlight(current, id)
    return Response(status_code=204)
