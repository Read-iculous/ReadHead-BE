"""Opt-in production middleware/limiter check against a disposable real Redis."""

import hashlib
import os
import time
from copy import copy
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from redis.asyncio import Redis

from app.core import limiter, middleware, redis
from app.core.config import get_settings
from app.main import app

REDIS_URL = os.getenv("READHEAD_INTEGRATION_REDIS_URL")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not REDIS_URL, reason="Set READHEAD_INTEGRATION_REDIS_URL to a disposable Redis"
)
async def test_real_redis_limit_returns_browser_readable_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use actual Redis Lua counts and HTTP headers; never access the database."""
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    identity = f"cors-regression-{uuid4().hex}"
    timestamp = int(time.time())
    key = f"rate:auth:{hashlib.sha256(identity.encode()).hexdigest()}:{timestamp // 60}"
    application = copy(app)
    application.middleware_stack = None
    monkeypatch.setattr(redis, "client", client)
    monkeypatch.setattr(limiter, "time", SimpleNamespace(time=lambda: timestamp))
    monkeypatch.setattr(
        middleware,
        "get_settings",
        lambda: get_settings().model_copy(update={"auth_requests_per_minute": 1}),
    )
    origin = "chrome-extension://" + "a" * 32
    try:
        assert await client.ping()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application, client=(identity, 12345)),
            base_url="http://test",
        ) as http:
            first = await http.post(
                "/api/v1/auth/login", json={}, headers={"Origin": origin}
            )
            second = await http.post(
                "/api/v1/auth/login", json={}, headers={"Origin": origin}
            )
        assert first.status_code == 422  # Missing credentials; no database query.
        assert await client.get(key) == "2"
        assert await client.ttl(key) > 0
        assert second.status_code == 429
        assert second.json()["code"] == "RATE_LIMIT_EXCEEDED"
        assert second.headers["access-control-allow-origin"] == origin
        assert second.headers["access-control-allow-credentials"] == "true"
        assert 1 <= int(second.headers["retry-after"]) <= 60
        assert second.headers["x-request-id"]
        exposed = {
            value.strip().lower()
            for value in second.headers["access-control-expose-headers"].split(",")
        }
        assert {"retry-after", "x-request-id"} <= exposed
    finally:
        try:
            await client.delete(key)
        finally:
            await client.aclose()
