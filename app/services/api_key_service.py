"""Validate BYOK credentials before encrypted atomic vault replacement."""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis
from app.core.ai.factory import ProviderFactory
from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.security import decrypt_secret, encrypt_secret, utcnow
from app.models.api_key import UserApiKey
from app.schemas.api_key import ApiKeyCreateRequest
from app.schemas.common import public

FIELDS = (
    "id",
    "provider",
    "key_hint",
    "is_active",
    "last_validated_at",
    "created_at",
    "updated_at",
)


async def active_key(db: AsyncSession, uid: UUID, provider: str) -> str:
    """Decrypt a single owned active key into request-local memory."""
    row = await db.scalar(
        select(UserApiKey).where(
            UserApiKey.user_id == uid,
            UserApiKey.provider == provider,
            UserApiKey.is_active.is_(True),
        )
    )
    if not row:
        raise AppException(
            400,
            "NO_ACTIVE_API_KEY",
            "Configure an active key for the selected provider",
        )
    return decrypt_secret(row.encrypted_key)


async def list_keys(principal: Principal) -> dict:
    """Return masked metadata; ciphertext is never serialized."""
    async with transaction() as db:
        rows = (
            await db.scalars(
                select(UserApiKey)
                .where(UserApiKey.user_id == principal.user_id)
                .order_by(UserApiKey.provider)
            )
        ).all()
        return {"data": [public(row, FIELDS) for row in rows]}


async def store(principal: Principal, data: ApiKeyCreateRequest) -> dict:
    """Preserve the existing key unless the replacement passes upstream validation."""
    raw = data.api_key.get_secret_value()
    try:
        await ProviderFactory.create(data.provider, raw).validate_key()
    except AppException as exc:
        if exc.code == "KEY_VALIDATION_FAILED":
            raise AppException(
                400, "KEY_VALIDATION_FAILED", "Provider rejected the new key"
            ) from exc
        raise
    now = utcnow()
    values = dict(
        encrypted_key=encrypt_secret(raw),
        key_hint=raw[:3] + "..." + raw[-4:],
        is_active=data.set_active,
        last_validated_at=now,
        updated_at=now,
    )
    mutex = redis.Mutex(f"lock:apikey:{principal.user_id}:{data.provider}")
    await mutex.acquire()
    try:
        async with transaction() as db:
            result = await db.execute(
                insert(UserApiKey)
                .values(user_id=principal.user_id, provider=data.provider, **values)
                .on_conflict_do_update(
                    index_elements=["user_id", "provider"], set_=values
                )
                .returning(UserApiKey)
            )
            return {"data": public(result.scalar_one(), FIELDS)}
    finally:
        await mutex.release()


async def remove(principal: Principal, provider: str) -> None:
    """Delete only this user's key for a provider."""
    mutex = redis.Mutex(f"lock:apikey:{principal.user_id}:{provider}")
    await mutex.acquire()
    try:
        async with transaction() as db:
            result = await db.execute(
                delete(UserApiKey)
                .where(
                    UserApiKey.user_id == principal.user_id,
                    UserApiKey.provider == provider,
                )
                .returning(UserApiKey.id)
            )
            if result.scalar_one_or_none() is None:
                raise AppException(404, "API_KEY_NOT_FOUND", "Stored key not found")
    finally:
        await mutex.release()


async def validate(principal: Principal, provider: str) -> dict:
    """Validate a stored key outside the database transaction."""
    async with transaction() as db:
        row = await db.scalar(
            select(UserApiKey).where(
                UserApiKey.user_id == principal.user_id, UserApiKey.provider == provider
            )
        )
        if not row:
            raise AppException(404, "API_KEY_NOT_FOUND", "Stored key not found")
        cipher = row.encrypted_key
        key = decrypt_secret(cipher)
    await ProviderFactory.create(provider, key).validate_key()
    async with transaction() as db:
        from sqlalchemy import update

        await db.execute(
            update(UserApiKey)
            .where(
                UserApiKey.user_id == principal.user_id,
                UserApiKey.provider == provider,
                UserApiKey.encrypted_key == cipher,
            )
            .values(last_validated_at=utcnow())
        )
    return {"data": dict(valid=True, message="Key validated successfully")}
