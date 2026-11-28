"""JWT authentication with authoritative database session validation."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.security import decode_token, utcnow
from app.models.auth_session import AuthSession
from app.models.user import User

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Detached identity safe to retain across an SSE request."""

    user_id: UUID
    session_id: UUID
    role: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    """Check account and auth-session state for every new request."""
    if credentials is None:
        raise AppException(
            401,
            "UNAUTHORIZED",
            "Bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = decode_token(credentials.credentials, "access")
    async with transaction() as db:
        user = await db.get(User, UUID(claims["sub"]))
        session = await db.get(AuthSession, UUID(claims["sid"]))
        if not user or not session or session.user_id != user.id:
            raise AppException(401, "UNAUTHORIZED", "Session no longer exists")
        if user.status != "active" or not user.is_active:
            raise AppException(401, "USER_SUSPENDED", "Account is not active")
        if session.revoked_at or session.expires_at <= utcnow():
            raise AppException(401, "UNAUTHORIZED", "Session has ended")
        return Principal(user.id, session.id, user.role)


async def require_admin(current: Principal = Depends(get_current_user)) -> Principal:
    """Restrict administrative resources to active administrators."""
    if current.role != "admin":
        raise AppException(403, "FORBIDDEN_RESOURCE", "Administrator access required")
    return current
