"""User profile, preferences and account data lifecycle."""

import asyncio

from sqlalchemy import select

from app.core import redis
from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.security import verify_password
from app.models.user import OAuthAccount, User
from app.schemas.common import public
from app.schemas.user import AccountDeleteRequest, UserSettingUpdateRequest
from app.services.auth_service import revoke_sessions
from app.services.common import (
    SETTINGS_FIELDS,
    USER_FIELDS,
    settings_for,
    settings_values,
    sync_stamp,
)


async def get_profile(principal: Principal) -> dict:
    """Return the current profile and provider names without credentials."""
    async with transaction() as db:
        user = await db.get(User, principal.user_id)
        if user is None:
            raise AppException(401, "UNAUTHORIZED", "Account no longer exists")
        result = public(user, USER_FIELDS)
        result["linked_accounts"] = list(
            (
                await db.scalars(
                    select(OAuthAccount.provider).where(OAuthAccount.user_id == user.id)
                )
            ).all()
        )
        return {"data": result}


async def get_settings(principal: Principal) -> dict:
    """Read the account's synchronized preferences."""
    async with transaction() as db:
        return {
            "data": public(await settings_for(db, principal.user_id), SETTINGS_FIELDS)
        }


async def update_settings(principal: Principal, data: UserSettingUpdateRequest) -> dict:
    """Apply an optimistic version-checked settings update."""
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        row = await settings_for(db, principal.user_id)
        if row.version != data.version:
            raise AppException(
                409,
                "SYNC_CONFLICT",
                "Settings were changed on another device",
                server_record=public(row, SETTINGS_FIELDS),
                client_version=data.version,
            )
        values = settings_values(
            row, data.model_dump(exclude_unset=True, exclude={"version"})
        )
        for key, value in values.items():
            setattr(row, key, value)
        row.version += 1
        row.updated_at = stamp
        await db.flush()
        return {"data": public(row, SETTINGS_FIELDS)}


async def delete_account(principal: Principal, data: AccountDeleteRequest) -> None:
    """Revoke all sessions and permanently cascade personal data."""
    async with transaction() as db:
        user = await db.scalar(
            select(User).where(User.id == principal.user_id).with_for_update()
        )
        if user is None:
            raise AppException(401, "UNAUTHORIZED", "Account no longer exists")
        if user.hashed_password:
            if not data.password or not await asyncio.to_thread(
                verify_password, data.password.get_secret_value(), user.hashed_password
            ):
                raise AppException(
                    401,
                    "INVALID_CREDENTIALS",
                    "Password confirmation failed",
                    "password",
                )
        # Hold the same user lock as quiz publication until cleanup and deletion finish.
        # Fail before committing deletion if personal cache cleanup cannot be confirmed.
        await redis.purge_private_quizzes(str(user.id))
        sids = await revoke_sessions(db, user.id)
        await db.delete(user)
    await redis.mark(f"revoked_users:{principal.user_id}")
    for sid in sids:
        await redis.purge_grace(str(sid))
