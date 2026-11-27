"""Authenticated profile, preferences and account lifecycle routes."""

from fastapi import APIRouter, Depends, Response

from app.core.auth import Principal, get_current_user
from app.schemas.responses import Envelope, UserResponse, UserSettingResponse
from app.schemas.user import AccountDeleteRequest, UserSettingUpdateRequest
from app.services import user_service

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/me", response_model=Envelope[UserResponse], response_model_exclude_none=False
)
async def profile(current: Principal = Depends(get_current_user)) -> dict:
    """Read the authenticated user's public profile."""
    return await user_service.get_profile(current)


@router.delete("/me", status_code=204)
async def delete_account(
    data: AccountDeleteRequest, current: Principal = Depends(get_current_user)
) -> Response:
    """Delete the account after explicit confirmation."""
    await user_service.delete_account(current, data)
    return Response(status_code=204)


@router.get(
    "/me/settings",
    response_model=Envelope[UserSettingResponse],
    response_model_exclude_none=False,
)
async def settings(current: Principal = Depends(get_current_user)) -> dict:
    """Read synchronized settings."""
    return await user_service.get_settings(current)


@router.patch(
    "/me/settings",
    response_model=Envelope[UserSettingResponse],
    response_model_exclude_none=False,
)
async def update_settings(
    data: UserSettingUpdateRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Apply a version-checked partial update."""
    return await user_service.update_settings(current, data)
