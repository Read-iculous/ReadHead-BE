"""Opt-in real PostgreSQL/Redis fixtures; external providers use wire mocks."""

import os
from collections.abc import AsyncIterator
from copy import copy
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import database, redis
from app.core.config import get_settings
from app.main import app
from app.models.user import User
from tests.integration.provider_wire import ProviderWire


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> ProviderWire:
    """Mock external HTTP responses while using installed SDK implementations."""
    fixture = ProviderWire()
    fixture.install(monkeypatch)
    return fixture


@pytest_asyncio.fixture
async def system(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SimpleNamespace]:
    """Use actual auth, services, SQL transactions and Redis with owned test accounts."""
    if os.getenv("READHEAD_FULL_INTEGRATION") != "1":
        pytest.skip(
            "Set READHEAD_FULL_INTEGRATION=1 with disposable DATABASE_URL/REDIS_URL"
        )
    cfg = get_settings()
    engine = create_async_engine(cfg.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    cache = Redis.from_url(cfg.redis_url, decode_responses=True)
    await cache.ping()
    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(redis, "client", cache)
    application = copy(app)
    application.middleware_stack = None
    emails: list[str] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:

        async def account(admin: bool = False) -> dict:
            email = f"flow-test-{uuid4().hex}@example.com"
            emails.append(email)
            password = "Disposable-flow-test-password-123"
            if admin:
                from app.cli.create_admin import create

                await create(email, password)
            else:
                created = await client.post(
                    "/api/v1/auth/register", json={"email": email, "password": password}
                )
                assert created.status_code == 201
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            )
            assert response.status_code == 200
            tokens = response.json()["data"]
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            profile = await client.get("/api/v1/users/me", headers=headers)
            assert profile.status_code == 200
            return dict(
                id=profile.json()["data"]["id"],
                email=email,
                password=password,
                headers=headers,
                tokens=tokens,
            )

        try:
            yield SimpleNamespace(
                http=client, db=sessions, cache=cache, account=account, emails=emails
            )
        finally:
            async with sessions.begin() as db:
                await db.execute(delete(User).where(User.email.in_(emails)))
            await cache.aclose()
            await engine.dispose()
