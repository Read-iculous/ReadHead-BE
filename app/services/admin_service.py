"""Administrative moderation and aggregate telemetry without reading content."""

from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy import select

from app.core import redis
from app.core.auth import Principal
from app.core.database import transaction
from app.core.exceptions import AppException
from app.core.privacy.pii_detector import inspect
from app.models.feedback import AiFeedback
from app.models.user import User
from app.schemas.admin import UserStatusUpdateRequest
from app.services.auth_service import revoke_sessions
from app.services.common import paginate


async def list_users(
    principal: Principal, page: int, page_size: int, status: str | None
) -> dict:
    """Return paginated account metadata without reading materials or secrets."""
    async with transaction() as db:
        q = select(User)
        if status:
            q = q.where(User.status == status)
        return await paginate(
            db,
            q.order_by(User.created_at.desc(), User.id),
            ("id", "email", "full_name", "role", "status", "created_at"),
            page,
            page_size,
        )


async def set_status(
    principal: Principal, uid: UUID, data: UserStatusUpdateRequest
) -> dict:
    """Revoke every session on suspension; reactivation never revives old tokens."""
    if uid == principal.user_id:
        raise AppException(
            400,
            "CANNOT_MODIFY_SELF_STATUS",
            "Administrators cannot modify their own status",
        )
    async with transaction() as db:
        user = await db.scalar(select(User).where(User.id == uid).with_for_update())
        if not user:
            raise AppException(404, "USER_NOT_FOUND", "User not found")
        user.status = data.status
        user.is_active = data.status == "active"
        from app.core.security import utcnow

        user.updated_at = utcnow()
        sids = await revoke_sessions(db, uid) if data.status != "active" else []
    await sync_user_revocation_marker(uid)
    for sid in sids:
        # Reactivation clears only the user marker; old sessions stay revoked.
        await redis.mark_session_revoked(str(sid))
        await redis.purge_grace(str(sid))
    return {"data": dict(user_id=uid, new_status=data.status)}


async def sync_user_revocation_marker(uid: UUID) -> None:
    """Publish the latest committed status while excluding concurrent status writers."""
    async with transaction() as db:
        # A delayed publisher must not replay its request's obsolete status. Keep
        # this lock through Redis I/O so a newer DB update cannot overtake it.
        user = await db.scalar(select(User).where(User.id == uid).with_for_update())
        if user is not None and user.status == "active" and user.is_active:
            try:
                await redis.client.delete(f"revoked_users:{uid}")
            except RedisError:
                pass
        else:
            # Missing users have been deleted and must remain revoked as well.
            await redis.mark(f"revoked_users:{uid}")


async def feedback(principal: Principal, page: int, page_size: int) -> dict:
    """Return voluntary feedback with heuristic redaction before presentation."""
    async with transaction() as db:
        result = await paginate(
            db,
            select(AiFeedback).order_by(AiFeedback.created_at.desc(), AiFeedback.id),
            ("id", "message_id", "rating", "report_reason", "comment", "created_at"),
            page,
            page_size,
        )
        for row in result["data"]["items"]:
            if row["comment"]:
                row["comment"] = inspect(row["comment"])[1]
        return result


async def telemetry(principal: Principal, timeframe: str) -> dict:
    """Read time-bucketed aggregate counters, never per-user conversations."""
    import time

    minutes = {"24h": 1440, "7d": 10080, "30d": 43200}[timeframe]
    end = int(time.time() // 60)
    totals: dict[str, float] = dict(
        requests=0, errors=0, latency_ms=0, openai=0, gemini=0, claude=0
    )
    try:
        for start in range(end - minutes + 1, end + 1, 500):
            async with redis.client.pipeline(transaction=False) as pipe:
                for minute in range(start, min(start + 500, end + 1)):
                    pipe.hgetall(f"metrics:{minute}")
                for row in await pipe.execute():
                    for key in totals:
                        totals[key] += float(row.get(key, 0))
    except RedisError as exc:
        raise AppException(
            503, "SERVICE_DEGRADED", "Telemetry counters are unavailable"
        ) from exc
    count = totals["requests"]
    providers = sum(totals[p] for p in ("openai", "gemini", "claude"))
    return {
        "data": dict(
            total_requests=int(count),
            provider_split={
                p: totals[p] / providers if providers else 0
                for p in ("openai", "gemini", "claude")
            },
            error_rate=totals["errors"] / count if count else 0,
            avg_latency_ms=totals["latency_ms"] / count if count else 0,
        )
    }
