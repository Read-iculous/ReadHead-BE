"""Unified incremental sync and atomic local mutation upload."""

from fastapi import APIRouter, Depends

from app.core.auth import Principal, get_current_user
from app.schemas.sync import SyncPullRequest, SyncPushRequest
from app.services import sync_service

router = APIRouter(prefix="/sync", tags=["Synchronization"])


@router.post("/pull")
async def pull(
    data: SyncPullRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Pull a page of latest state using one opaque cursor."""
    return await sync_service.pull(current, data)


@router.post("/push")
async def push(
    data: SyncPushRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Apply a bounded batch without silent version overwrites."""
    return await sync_service.push(current, data)
