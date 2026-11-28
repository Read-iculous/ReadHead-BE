"""Public registration, login, OAuth and session token endpoints."""

from fastapi import APIRouter, Depends, Request, Response

from app.core.auth import Principal, get_current_user
from app.schemas.auth import (
    GitHubAuthRequest,
    GoogleAuthRequest,
    TokenRefreshRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.schemas.responses import Envelope, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    status_code=201,
    response_model=Envelope[UserResponse],
    response_model_exclude_none=False,
)
async def register(data: UserRegisterRequest) -> dict:
    """Register an account with default settings."""
    return await auth_service.register(data)


@router.post(
    "/login", response_model=Envelope[TokenResponse], response_model_exclude_none=False
)
async def login(data: UserLoginRequest, request: Request) -> dict:
    """Issue a revocable session token pair."""
    return await auth_service.login(data, request.headers.get("user-agent"))


@router.post(
    "/oauth/google",
    response_model=Envelope[TokenResponse],
    response_model_exclude_none=False,
)
async def google(data: GoogleAuthRequest, request: Request) -> dict:
    """Verify a Google ID token and link a verified account."""
    return await auth_service.oauth(
        "google", data.id_token.get_secret_value(), request.headers.get("user-agent")
    )


@router.post(
    "/oauth/github",
    response_model=Envelope[TokenResponse],
    response_model_exclude_none=False,
)
async def github(data: GitHubAuthRequest, request: Request) -> dict:
    """Exchange a GitHub code and require a verified primary email."""
    return await auth_service.oauth(
        "github", data.code.get_secret_value(), request.headers.get("user-agent")
    )


@router.post(
    "/refresh",
    response_model=Envelope[TokenResponse],
    response_model_exclude_none=False,
)
async def refresh(data: TokenRefreshRequest) -> dict:
    """Rotate within the existing auth session."""
    return await auth_service.refresh(data.refresh_token.get_secret_value())


@router.post("/logout", status_code=204)
async def logout(
    data: TokenRefreshRequest, current: Principal = Depends(get_current_user)
) -> Response:
    """Revoke this session's entire refresh-token chain."""
    await auth_service.logout(current, data.refresh_token.get_secret_value())
    return Response(status_code=204)
