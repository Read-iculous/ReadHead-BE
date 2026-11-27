"""Encrypted BYOK key vault metadata and validation routes."""

from fastapi import APIRouter, Depends, Response

from app.core.auth import Principal, get_current_user
from app.schemas.api_key import ApiKeyCreateRequest
from app.schemas.common import Provider
from app.schemas.responses import ApiKeyResponse, Envelope
from app.services import api_key_service

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


@router.get(
    "", response_model=Envelope[list[ApiKeyResponse]], response_model_exclude_none=False
)
async def list_keys(current: Principal = Depends(get_current_user)) -> dict:
    """List masked provider credentials."""
    return await api_key_service.list_keys(current)


@router.post(
    "",
    status_code=201,
    response_model=Envelope[ApiKeyResponse],
    response_model_exclude_none=False,
)
async def store(
    data: ApiKeyCreateRequest, current: Principal = Depends(get_current_user)
) -> dict:
    """Validate then atomically upsert one encrypted provider key."""
    return await api_key_service.store(current, data)


@router.delete("/{provider}", status_code=204)
async def remove(
    provider: Provider, current: Principal = Depends(get_current_user)
) -> Response:
    """Delete a provider key owned by this user."""
    await api_key_service.remove(current, provider)
    return Response(status_code=204)


@router.post("/{provider}/validate")
async def validate(
    provider: Provider, current: Principal = Depends(get_current_user)
) -> dict:
    """Check stored key validity without returning it."""
    return await api_key_service.validate(current, provider)
