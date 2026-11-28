"""Shared tenant isolation, serialization, pagination and sync timestamp utilities."""

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.models.user import User
from app.models.user_setting import UserSetting

USER_FIELDS = (
    "id",
    "email",
    "full_name",
    "avatar_url",
    "role",
    "status",
    "is_verified",
    "created_at",
)
SETTINGS_FIELDS = (
    "id",
    "default_provider",
    "default_model",
    "target_language",
    "explanation_level",
    "accessibility_profile",
    "proactive_assistance_enabled",
    "proactive_sensitivity",
    "data_protection_mode",
    "privacy_mode_enabled",
    "blacklisted_domains",
    "version",
    "updated_at",
)
CONVERSATION_FIELDS = (
    "id",
    "title",
    "page_url",
    "page_title",
    "reading_session_id",
    "version",
    "is_deleted",
    "created_at",
    "updated_at",
)
MESSAGE_FIELDS = (
    "id",
    "sender_role",
    "content",
    "selected_context",
    "provider_used",
    "model_used",
    "is_grounded",
    "uncertainty_flag",
    "grounding_notes",
    "created_at",
)
HIGHLIGHT_FIELDS = (
    "id",
    "page_url",
    "highlighted_text",
    "user_note",
    "color",
    "version",
    "is_deleted",
    "created_at",
    "updated_at",
)
HISTORY_FIELDS = (
    "id",
    "page_url",
    "page_title",
    "cached_summary",
    "reading_time_seconds",
    "is_bookmarked",
    "visited_at",
)


async def lock_user(db: AsyncSession, user_id: UUID) -> User:
    """Refresh and lock the user before acquiring any session/entity row locks."""
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise AppException(401, "UNAUTHORIZED", "Account no longer exists")
    return user


async def sync_stamp(db: AsyncSession, user_id: UUID) -> datetime:
    """Serialize tenant mutations and allocate a monotonic timestamp after locking."""
    user = await lock_user(db, user_id)
    now = await db.scalar(select(func.clock_timestamp()))
    if now is None:
        raise AppException(500, "DATABASE_ERROR", "Database clock unavailable")
    user.sync_clock = max(now, user.sync_clock + timedelta(microseconds=1))
    await db.flush()
    return user.sync_clock


async def settings_for(db: AsyncSession, user_id: UUID) -> UserSetting:
    """Load the settings initialized together with account creation."""
    row = await db.scalar(
        select(UserSetting)
        .where(UserSetting.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise AppException(500, "DATABASE_ERROR", "Account settings are unavailable")
    return row


def settings_values(row: UserSetting, values: dict) -> dict:
    """Normalize settings mutations identically for PATCH and sync push."""
    from app.core.ai.factory import DEFAULT_MODELS

    values = values.copy()
    if (
        "default_provider" in values
        and values["default_provider"] != row.default_provider
        and "default_model" not in values
    ):
        values["default_model"] = DEFAULT_MODELS[values["default_provider"]]
    if "accessibility_profile" in values:
        values["accessibility_profile"] = {
            **row.accessibility_profile,
            **values["accessibility_profile"],
        }
    return values


async def owned(
    db: AsyncSession,
    model: Any,
    entity_id: UUID,
    user_id: UUID,
    code: str,
    lock: bool = False,
) -> Any:
    """Retrieve a tenant-owned resource without disclosing another tenant's IDs."""
    query = select(model).where(model.id == entity_id, model.user_id == user_id)
    if hasattr(model, "is_deleted"):
        query = query.where(model.is_deleted.is_(False))
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = await db.scalar(query)
    if row is None:
        raise AppException(404, code, "Resource not found")
    return row


async def paginate(
    db: AsyncSession, query: Any, fields: tuple, page: int, page_size: int
) -> dict:
    """Return the documented nested pagination envelope."""
    from app.schemas.common import public

    total = (
        await db.scalar(
            select(func.count()).select_from(query.order_by(None).subquery())
        )
        or 0
    )
    rows = (
        await db.scalars(query.offset((page - 1) * page_size).limit(page_size))
    ).all()
    return dict(
        data=dict(
            items=[public(r, fields) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size,
        )
    )
