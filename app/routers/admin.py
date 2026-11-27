"""Administrator-only account moderation and sanitized operational views."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.auth import Principal, require_admin
from app.schemas.admin import UserStatusUpdateRequest
from app.services import admin_service

router = APIRouter(prefix="/admin", tags=["Administration"])


@router.get("/telemetry")
async def telemetry(
    timeframe: Literal["24h", "7d", "30d"] = "24h",
    current: Principal = Depends(require_admin),
) -> dict:
    """Read aggregate request, provider and error metrics."""
    return await admin_service.telemetry(current, timeframe)


@router.get("/users")
async def users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Literal["active", "suspended", "banned"] | None = None,
    current: Principal = Depends(require_admin),
) -> dict:
    """List account metadata without private reading history."""
    return await admin_service.list_users(current, page, page_size, status)


@router.patch("/users/{id}/status")
async def status(
    id: UUID, data: UserStatusUpdateRequest, current: Principal = Depends(require_admin)
) -> dict:
    """Suspend, ban or reactivate another account."""
    return await admin_service.set_status(current, id, data)


@router.get("/feedback")
async def feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current: Principal = Depends(require_admin),
) -> dict:
    """Read voluntary feedback after PII redaction."""
    return await admin_service.feedback(current, page, page_size)
