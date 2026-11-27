"""Account creation, provider login and session-scoped token lifecycle."""

import asyncio
import secrets
from datetime import timedelta
from uuid import UUID, uuid4

import httpx
from pydantic import TypeAdapter
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis
from app.core.auth import Principal
from app.core.config import get_settings
from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.security import (
    decode_token,
    hash_password,
    make_pair,
    token_hash,
    utcnow,
    verify_password,
)
from app.models.auth_session import AuthSession
from app.models.refresh_token import RefreshToken
from app.models.user import OAuthAccount, User
from app.models.user_setting import UserSetting
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.schemas.common import public
from app.schemas.oauth import GitHubEmail, GitHubIdentity, GitHubToken, GoogleIdentity
from app.services.common import USER_FIELDS, lock_user, sync_stamp

DUMMY_HASH = hash_password("unavailable-account-password")


async def register(data: UserRegisterRequest) -> dict:
    """Create a unique account and its default versioned settings."""
    hashed = await asyncio.to_thread(hash_password, data.password.get_secret_value())
    try:
        async with transaction() as db:
            user = User(
                email=data.email, hashed_password=hashed, full_name=data.full_name
            )
            db.add(user)
            await db.flush()
            stamp = await sync_stamp(db, user.id)
            db.add(UserSetting(user_id=user.id, updated_at=stamp))
            await db.flush()
            return {"data": public(user, USER_FIELDS)}
    except IntegrityError as exc:
        raise AppException(
            409, "EMAIL_ALREADY_EXISTS", "Email is already registered", "email"
        ) from exc


async def issue_session(db: AsyncSession, user: User, device: str | None) -> dict:
    """Persist one login session and the hash of its first refresh JWT."""
    # Bcrypt/provider verification can overlap a ban/delete; discard the old snapshot.
    user = await lock_user(db, user.id)
    if user.status != "active" or not user.is_active:
        raise AppException(401, "USER_SUSPENDED", "Account is not active")
    sid, rid = uuid4(), uuid4()
    pair, expiry = make_pair(user.id, sid, rid)
    db.add(
        AuthSession(
            id=sid, user_id=user.id, expires_at=expiry, device_info=(device or "")[:255]
        )
    )
    await db.flush()
    db.add(
        RefreshToken(
            id=rid,
            user_id=user.id,
            session_id=sid,
            token_hash=token_hash(pair["refresh_token"]),
            expires_at=expiry,
            device_info=(device or "")[:255],
        )
    )
    return {"data": pair}


async def login(data: UserLoginRequest, device: str | None) -> dict:
    """Verify credentials without revealing whether an email exists."""
    async with transaction() as db:
        user = await db.scalar(
            select(User).where(User.email == data.email.strip().casefold())
        )
        hashed = user.hashed_password if user and user.hashed_password else DUMMY_HASH
        valid = await asyncio.to_thread(
            verify_password, data.password.get_secret_value(), hashed
        )
        if not user or not user.hashed_password or not valid:
            raise AppException(
                401, "INVALID_CREDENTIALS", "Incorrect email or password"
            )
        return await issue_session(db, user, device)


async def checked_session(
    db: AsyncSession, user_id: UUID, sid: UUID, lock: bool = True
) -> tuple[AuthSession, User]:
    """Revalidate authoritative session and account state after acquiring locks."""
    user = (
        await lock_user(db, user_id)
        if lock
        else await db.get(User, user_id, populate_existing=True)
    )
    q = select(AuthSession).where(AuthSession.id == sid, AuthSession.user_id == user_id)
    if lock:
        q = q.with_for_update()
    session = await db.scalar(q.execution_options(populate_existing=True))
    if not user or not session:
        raise AppException(401, "UNAUTHORIZED", "Session no longer exists")
    if user.status != "active" or not user.is_active:
        raise AppException(401, "USER_SUSPENDED", "Account is not active")
    if session.revoked_at:
        raise AppException(401, "REFRESH_TOKEN_REVOKED", "Session has been revoked")
    if session.expires_at <= utcnow():
        raise AppException(401, "REFRESH_TOKEN_EXPIRED", "Session has expired")
    return session, user


async def cached_pair(
    db: AsyncSession, uid: UUID, sid: UUID, old_hash: str
) -> dict | None:
    """Follow cached rotations only while every successor belongs to an active session."""
    await checked_session(db, uid, sid)
    seen = set()
    while old_hash not in seen:
        seen.add(old_hash)
        cached = await redis.get_json(f"refresh_grace:{sid}:{old_hash}")
        if not cached or cached.get("sid") != str(sid):
            return None
        try:
            rid = UUID(cached["replacement_token_id"])
            pair = cached["token_pair"]
            row = await db.get(RefreshToken, rid, populate_existing=True)
            if not row or row.session_id != sid or row.expires_at <= utcnow():
                return None
            if not secrets.compare_digest(
                row.token_hash, token_hash(pair["refresh_token"])
            ):
                return None
            if not row.is_revoked:
                return {"data": pair}
            if row.revocation_reason != "rotated":
                return None
            old_hash = row.token_hash
        except (KeyError, ValueError, TypeError):
            return None
    return None


async def refresh(raw: str) -> dict:
    """Rotate atomically with grace replay and failure-isolated fallback."""
    claims = decode_token(raw, "refresh")
    uid, sid, digest = UUID(claims["sub"]), UUID(claims["sid"]), token_hash(raw)
    async with transaction() as db:
        cached = await cached_pair(db, uid, sid, digest)
        if cached:
            return cached
    mutex = redis.Mutex(f"lock:refresh:{sid}:{digest}")
    await mutex.acquire()
    try:
        async with transaction() as db:
            session, _ = await checked_session(db, uid, sid)
            cached = await cached_pair(db, uid, sid, digest)
            if cached:
                return cached
            row = await db.scalar(
                select(RefreshToken)
                .where(
                    RefreshToken.id == UUID(claims["jti"]),
                    RefreshToken.session_id == sid,
                    RefreshToken.token_hash == digest,
                )
                .with_for_update()
            )
            if not row or not secrets.compare_digest(row.token_hash, digest):
                raise AppException(
                    401, "TOKEN_INVALID", "Refresh token is not recognized"
                )
            if row.is_revoked:
                if (
                    row.revocation_reason == "rotated"
                    and row.revoked_at
                    and utcnow() - row.revoked_at < timedelta(seconds=30)
                ):
                    raise AppException(
                        503,
                        "REFRESH_TEMPORARILY_UNAVAILABLE",
                        "Refresh result temporarily unavailable; consult shared token store or sign in again",
                        headers={"Retry-After": "1"},
                    )
                raise AppException(
                    401, "REFRESH_TOKEN_REVOKED", "Refresh token is no longer active"
                )
            rid = uuid4()
            pair, expiry = make_pair(uid, sid, rid)
            db.add(
                RefreshToken(
                    id=rid,
                    user_id=uid,
                    session_id=sid,
                    token_hash=token_hash(pair["refresh_token"]),
                    expires_at=expiry,
                    device_info=row.device_info,
                )
            )
            await db.flush()
            result = await db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.id == row.id,
                    RefreshToken.session_id == sid,
                    RefreshToken.is_revoked.is_(False),
                )
                .values(
                    is_revoked=True,
                    revocation_reason="rotated",
                    revoked_at=utcnow(),
                    replaced_by_token_id=rid,
                )
                .returning(RefreshToken.id)
            )
            if result.scalar_one_or_none() is None:
                raise AppException(
                    503,
                    "REFRESH_TEMPORARILY_UNAVAILABLE",
                    "Concurrent refresh; try again",
                    headers={"Retry-After": "1"},
                )
            session.expires_at = expiry
        await redis.cache_pair(
            str(sid),
            digest,
            dict(sid=str(sid), replacement_token_id=str(rid), token_pair=pair),
        )
        return {"data": pair}
    finally:
        await mutex.release()


async def revoke_sessions(
    db: AsyncSession, uid: UUID, reason: str = "security", sid: UUID | None = None
) -> list[UUID]:
    """Lock sessions in stable order and revoke their active token chains."""
    await lock_user(db, uid)
    q = (
        select(AuthSession)
        .where(AuthSession.user_id == uid)
        .order_by(AuthSession.id)
        .with_for_update()
    )
    if sid:
        q = q.where(AuthSession.id == sid)
    sessions = (await db.scalars(q)).all()
    for row in sessions:
        if not row.revoked_at:
            row.revoked_at, row.revocation_reason = utcnow(), reason
    ids = [s.id for s in sessions]
    if ids:
        await db.execute(
            update(RefreshToken)
            .where(RefreshToken.session_id.in_(ids), RefreshToken.is_revoked.is_(False))
            .values(is_revoked=True, revoked_at=utcnow(), revocation_reason=reason)
        )
    return ids


async def logout(principal: Principal, raw: str) -> None:
    """End this session and all predecessor grace mappings, not other devices."""
    claims = decode_token(raw, "refresh")
    if claims["sub"] != str(principal.user_id) or claims["sid"] != str(
        principal.session_id
    ):
        raise AppException(
            403, "FORBIDDEN_RESOURCE", "Token belongs to a different session"
        )
    async with transaction() as db:
        row = await db.scalar(
            select(RefreshToken).where(
                RefreshToken.session_id == principal.session_id,
                RefreshToken.token_hash == token_hash(raw),
            )
        )
        if not row:
            raise AppException(401, "TOKEN_INVALID", "Refresh token is not recognized")
        await revoke_sessions(db, principal.user_id, "logout", principal.session_id)
    await redis.mark_session_revoked(str(principal.session_id))
    await redis.purge_grace(str(principal.session_id))


async def oauth(provider: str, raw: str, device: str | None) -> dict:
    """Verify an external identity and link only a verified email."""
    cfg = get_settings()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if provider == "google":
                if not cfg.google_client_id:
                    raise AppException(
                        503, "SERVICE_DEGRADED", "Google login is not configured"
                    )
                response = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo", params={"id_token": raw}
                )
                response.raise_for_status()
                identity = GoogleIdentity.model_validate(response.json())
                if (
                    identity.aud != cfg.google_client_id
                    or identity.iss
                    not in {"accounts.google.com", "https://accounts.google.com"}
                    or identity.exp <= utcnow().timestamp()
                ):
                    raise AppException(401, "TOKEN_INVALID", "Invalid Google identity")
                if not identity.email_verified:
                    raise AppException(
                        403, "EMAIL_NOT_VERIFIED", "Provider email is not verified"
                    )
                pid, email, name, avatar = (
                    identity.sub,
                    identity.email,
                    identity.name,
                    identity.picture,
                )
            else:
                if (
                    not cfg.github_client_id
                    or not cfg.github_client_secret.get_secret_value()
                ):
                    raise AppException(
                        503, "SERVICE_DEGRADED", "GitHub login is not configured"
                    )
                response = await client.post(
                    "https://github.com/login/oauth/access_token",
                    json=dict(
                        client_id=cfg.github_client_id,
                        client_secret=cfg.github_client_secret.get_secret_value(),
                        code=raw,
                    ),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                token = GitHubToken.model_validate(response.json()).access_token
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                }
                profile = await client.get(
                    "https://api.github.com/user", headers=headers
                )
                emails = await client.get(
                    "https://api.github.com/user/emails", headers=headers
                )
                profile.raise_for_status()
                emails.raise_for_status()
                github_identity = GitHubIdentity.model_validate(profile.json())
                verified_emails = TypeAdapter(list[GitHubEmail]).validate_python(
                    emails.json()
                )
                primary_email = next(
                    (
                        row.email
                        for row in verified_emails
                        if row.primary and row.verified
                    ),
                    None,
                )
                if not primary_email:
                    raise AppException(
                        400,
                        "OAUTH_EMAIL_MISSING",
                        "No verified primary email is available",
                    )
                email = primary_email
                pid, name, avatar = (
                    str(github_identity.id),
                    github_identity.name,
                    github_identity.avatar_url,
                )
    except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
        raise AppException(
            401, "TOKEN_INVALID", "Provider authentication failed"
        ) from exc
    async with transaction() as db:
        account = await db.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider, OAuthAccount.provider_user_id == pid
            )
        )
        if account:
            user = await db.get(User, account.user_id)
        else:
            email = email.strip().casefold()
            uid = uuid4()
            created = await db.scalar(
                insert(User)
                .values(
                    id=uid,
                    email=email,
                    full_name=(name or "")[:150],
                    avatar_url=avatar,
                    is_verified=True,
                )
                .on_conflict_do_nothing(index_elements=["email"])
                .returning(User.id)
            )
            user = await db.scalar(
                select(User).where(User.email == email).with_for_update()
            )
            if user is None:
                raise AppException(
                    401, "TOKEN_INVALID", "Unable to link provider account"
                )
            if created:
                stamp = await sync_stamp(db, user.id)
                db.add(UserSetting(user_id=user.id, updated_at=stamp))
            user.is_verified = True
            await db.execute(
                insert(OAuthAccount)
                .values(user_id=user.id, provider=provider, provider_user_id=pid)
                .on_conflict_do_nothing(index_elements=["provider", "provider_user_id"])
            )
            linked = await db.scalar(
                select(OAuthAccount).where(
                    OAuthAccount.provider == provider,
                    OAuthAccount.provider_user_id == pid,
                )
            )
            if linked is None or linked.user_id != user.id:
                raise AppException(
                    401, "TOKEN_INVALID", "Provider identity is already linked"
                )
        if user is None:
            raise AppException(401, "TOKEN_INVALID", "Provider account is unavailable")
        return await issue_session(db, user, device)
