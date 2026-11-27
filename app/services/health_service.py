"""Bounded readiness checks and dependency-free liveness."""

import asyncio
import time

from sqlalchemy import text

from app.core import redis
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import utcnow

STARTED = time.monotonic()


async def health() -> tuple[dict, int]:
    """Treat PostgreSQL as mandatory and Redis as a soft dependency."""

    async def ping(name: str) -> tuple[str, dict]:
        started = time.monotonic()
        try:
            if name == "database":

                async def database_ping() -> None:
                    async with SessionLocal() as db:
                        await db.execute(text("SELECT 1"))

                await asyncio.wait_for(database_ping(), 1.5)
            else:
                await asyncio.wait_for(redis.client.ping(), 1.5)
            return name, dict(
                status="healthy",
                latency_ms=round((time.monotonic() - started) * 1000, 2),
            )
        except Exception:
            return name, dict(status="unhealthy", error="Dependency unavailable")

    checks = dict(await asyncio.gather(ping("database"), ping("redis")))
    db_ok = checks["database"]["status"] == "healthy"
    state = (
        "unhealthy"
        if not db_ok
        else ("healthy" if checks["redis"]["status"] == "healthy" else "degraded")
    )
    return dict(
        status=state,
        environment=get_settings().environment,
        version="0.1.0",
        uptime_seconds=int(time.monotonic() - STARTED),
        checks=checks,
        timestamp=utcnow(),
    ), (200 if db_ok else 503)
