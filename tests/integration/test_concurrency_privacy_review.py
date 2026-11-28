"""Review regressions with actual PostgreSQL locks, Redis and HTTP boundaries."""

import asyncio
import threading
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text

from app.core.ai.factory import DEFAULT_MODELS
from app.core.auth import Principal
from app.core.security import decode_token
from app.models.auth_session import AuthSession
from app.models.conversation import Conversation, Message
from app.models.user import User
from app.schemas.ai import AiStreamRequest
from app.services import admin_service, ai_service, auth_service, user_service
from tests.integration.test_ai_quiz_oauth_admin import (
    QUIZ,
    SOURCE,
    sse_events,
    store_key,
)


async def wait_for_pg_block(system, blocker: int) -> None:
    """Wait for a real database lock wait rather than relying on a timing sleep."""

    async def observe() -> None:
        while True:
            async with system.db() as db:
                waiting = await db.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE :pid = ANY(pg_blocking_pids(pid)))"
                    ),
                    {"pid": blocker},
                )
            if waiting:
                return
            await asyncio.sleep(0.02)

    await asyncio.wait_for(observe(), timeout=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["suspend", "delete"])
async def test_refresh_and_moderation_obey_user_then_session_lock_order(
    system, monkeypatch, action
) -> None:
    admin, account = await system.account(admin=True), await system.account()
    user_locked, proceed = asyncio.Event(), asyncio.Event()
    module = admin_service if action == "suspend" else user_service
    original = module.revoke_sessions
    blocker = []

    async def gated_revoke(db, *args, **kwargs):
        blocker.append(await db.scalar(text("SELECT pg_backend_pid()")))
        user_locked.set()
        await proceed.wait()
        return await original(db, *args, **kwargs)

    monkeypatch.setattr(module, "revoke_sessions", gated_revoke)
    if action == "suspend":
        moderation = asyncio.create_task(
            system.http.patch(
                f"/api/v1/admin/users/{account['id']}/status",
                headers=admin["headers"],
                json={"status": "suspended"},
            )
        )
    else:
        moderation = asyncio.create_task(
            system.http.request(
                "DELETE",
                "/api/v1/users/me",
                headers=account["headers"],
                json={
                    "confirmation": "DELETE_ACCOUNT",
                    "password": account["password"],
                },
            )
        )
    rotation = None
    try:
        await asyncio.wait_for(user_locked.wait(), timeout=10)
        rotation = asyncio.create_task(
            system.http.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": account["tokens"]["refresh_token"]},
            )
        )
        await wait_for_pg_block(system, blocker[0])
    finally:
        proceed.set()
        pending = [moderation] + ([rotation] if rotation else [])
        responses = await asyncio.wait_for(asyncio.gather(*pending), timeout=15)
    assert responses[0].status_code == (200 if action == "suspend" else 204)
    assert responses[1].status_code == 401
    assert responses[1].json()["code"] in {"USER_SUSPENDED", "UNAUTHORIZED"}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["suspend", "delete"])
async def test_login_rechecks_user_after_password_thread_before_issuing_session(
    system, monkeypatch, action
) -> None:
    admin, account = await system.account(admin=True), await system.account()
    verifying, release = threading.Event(), threading.Event()
    verify = auth_service.verify_password

    def delayed_verify(raw: str, hashed: str) -> bool:
        verifying.set()
        if not release.wait(timeout=15):
            raise RuntimeError("Password test barrier timed out")
        return verify(raw, hashed)

    monkeypatch.setattr(auth_service, "verify_password", delayed_verify)
    login = asyncio.create_task(
        system.http.post(
            "/api/v1/auth/login",
            json={"email": account["email"], "password": account["password"]},
        )
    )
    try:
        assert await asyncio.to_thread(verifying.wait, 10)
        if action == "suspend":
            changed = await system.http.patch(
                f"/api/v1/admin/users/{account['id']}/status",
                headers=admin["headers"],
                json={"status": "suspended"},
            )
            assert changed.status_code == 200
        else:
            deleted = await system.http.request(
                "DELETE",
                "/api/v1/users/me",
                headers=account["headers"],
                json={
                    "confirmation": "DELETE_ACCOUNT",
                    "password": account["password"],
                },
            )
            assert deleted.status_code == 204
    finally:
        release.set()
        response = await asyncio.wait_for(login, timeout=10)
    assert response.status_code == 401
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(
                    AuthSession.user_id == UUID(account["id"]),
                    AuthSession.revoked_at.is_(None),
                )
            )
            == 0
        )


@pytest.mark.asyncio
async def test_privacy_enabled_between_initial_settings_read_and_stream_admission(
    system, wire, monkeypatch
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    original = ai_service.active_key

    async def enable_after_read(db, uid, provider):
        key = await original(db, uid, provider)
        changed = await system.http.patch(
            "/api/v1/users/me/settings",
            headers=account["headers"],
            json={"version": 1, "privacy_mode_enabled": True},
        )
        assert changed.status_code == 200
        return key

    monkeypatch.setattr(ai_service, "active_key", enable_after_read)
    response = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="explain",
            page_url="https://example.com/source",
            page_content=SOURCE,
            provider="openai",
            model="test-model",
        ),
    )
    assert sse_events(response)[-1][0] == "done"
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == UUID(account["id"]))
            )
            == 0
        )


@pytest.mark.asyncio
async def test_privacy_enabled_during_stream_prevents_assistant_write(
    system, wire
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")

    async def enable(index: int) -> None:
        if index == 0:
            response = await system.http.patch(
                "/api/v1/users/me/settings",
                headers=account["headers"],
                json={"version": 1, "privacy_mode_enabled": True},
            )
            assert response.status_code == 200

    wire.before_chunk = enable
    response = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="explain",
            page_url="https://example.com/source",
            page_content=SOURCE,
            provider="openai",
            model="test-model",
        ),
    )
    events = sse_events(response)
    assert events[-1][0] == "done"
    async with system.db() as db:
        roles = (
            await db.scalars(
                select(Message.sender_role).where(
                    Message.conversation_id == UUID(events[0][1]["conversation_id"])
                )
            )
        ).all()
        assert roles == [
            "user"
        ]  # This input committed before Privacy Mode was enabled.


@pytest.mark.asyncio
@pytest.mark.parametrize("enable_privacy", [True, False])
async def test_disconnect_rechecks_current_privacy_before_partial_write(
    system, wire, enable_privacy
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    claims = decode_token(account["tokens"]["access_token"], "access")
    principal = Principal(UUID(account["id"]), UUID(claims["sid"]), "user")
    prepared = await ai_service.prepare(
        principal,
        AiStreamRequest(
            task="explain",
            page_url="https://example.com/source",
            page_content=SOURCE,
            provider="openai",
            model="test-model",
        ),
    )
    stream = ai_service.generate(principal, prepared)
    try:
        assert (await anext(stream)).startswith("event: start")
        assert (await anext(stream)).startswith("event: token")
        if enable_privacy:
            changed = await system.http.patch(
                "/api/v1/users/me/settings",
                headers=account["headers"],
                json={"version": 1, "privacy_mode_enabled": True},
            )
            assert changed.status_code == 200
        with pytest.raises(asyncio.CancelledError):
            await stream.athrow(asyncio.CancelledError())
    finally:
        await stream.aclose()
    async with system.db() as db:
        assistants = (
            await db.scalars(
                select(Message).where(
                    Message.conversation_id == prepared.cid,
                    Message.sender_role == "assistant",
                )
            )
        ).all()
        assert len(assistants) == (0 if enable_privacy else 1)
        if assistants:
            assert assistants[0].grounding_notes == "interrupted_by_client"
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["patch", "sync"])
@pytest.mark.parametrize("provider", ["openai", "claude"])
async def test_provider_only_settings_change_chooses_matching_model(
    system, wire, route, provider
) -> None:
    account = await system.account()
    await store_key(system, account, provider)
    settings = (
        await system.http.get("/api/v1/users/me/settings", headers=account["headers"])
    ).json()["data"]
    if route == "patch":
        response = await system.http.patch(
            "/api/v1/users/me/settings",
            headers=account["headers"],
            json={"version": 1, "default_provider": provider},
        )
    else:
        response = await system.http.post(
            "/api/v1/sync/push",
            headers=account["headers"],
            json={
                "mutations": [
                    dict(
                        entity_type="settings",
                        entity_id=settings["id"],
                        action="update",
                        base_version=1,
                        payload={"default_provider": provider},
                    )
                ]
            },
        )
    assert response.status_code == 200
    current = (
        await system.http.get("/api/v1/users/me/settings", headers=account["headers"])
    ).json()["data"]
    assert current["default_model"] == DEFAULT_MODELS[provider]
    for endpoint, payload in [
        (
            "/api/v1/ai/stream",
            dict(
                task="explain",
                page_url="https://example.com/source",
                page_content=SOURCE,
            ),
        ),
        (
            "/api/v1/quiz/generate",
            dict(page_url="https://example.com/source", page_text=SOURCE),
        ),
        (
            "/api/v1/ai/proactive-suggest",
            dict(
                page_url="https://example.com/source",
                paragraph_text=SOURCE,
                dwell_time_seconds=30,
            ),
        ),
    ]:
        if endpoint.endswith("generate"):
            import json

            wire.output = json.dumps(QUIZ)
        else:
            wire.output = "A supported explanation [p-1]."
        response = await system.http.post(
            endpoint, headers=account["headers"], json=payload
        )
        assert response.status_code == 200
        assert wire.calls[-1]["body"]["model"] == DEFAULT_MODELS[provider]


@pytest.mark.asyncio
async def test_unicode_blacklist_blocks_history_and_ai_before_dispatch(
    system, wire
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    changed = await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json={"version": 1, "blacklisted_domains": ["*.bücher.de"]},
    )
    assert changed.status_code == 200
    calls = len(wire.calls)
    for host in ["bücher.de", "xn--bcher-kva.de", "read.bücher.de"]:
        url = f"https://{host}/article"
        history = await system.http.post(
            "/api/v1/reading/history",
            headers=account["headers"],
            json={"page_url": url},
        )
        assert history.status_code == 200 and history.json()["data"] is None
        ai = await system.http.post(
            "/api/v1/ai/stream",
            headers=account["headers"],
            json=dict(
                task="explain",
                page_url=url,
                page_content=SOURCE,
                provider="openai",
                model="test-model",
            ),
        )
        assert (
            ai.status_code == 400 and ai.json()["code"] == "DOMAIN_BLOCKED_BY_PRIVACY"
        )
    assert len(wire.calls) == calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/login/"]
)
async def test_public_auth_uses_same_ip_bucket_with_or_without_valid_bearer(
    system, monkeypatch, path
) -> None:
    from app.core import middleware
    from app.core.exceptions import AppException

    identities = []

    account = await system.account()

    async def capture(identity, group, limit):
        identities.append(identity)
        raise AppException(429, "RATE_LIMIT_EXCEEDED", "Test boundary")

    monkeypatch.setattr(middleware, "enforce_rate", capture)
    for headers in [{}, account["headers"]]:
        response = await system.http.post(path, headers=headers, json={})
        assert response.status_code == 429
    assert identities == ["127.0.0.1", "127.0.0.1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["x", "x" * 5000])
async def test_delete_password_overflow_is_rejected_without_deleting_account(
    system, suffix
) -> None:
    email, password = f"delete-check-{uuid4().hex}@example.com", "😀" * 18
    system.emails.append(email)
    created = await system.http.post(
        "/api/v1/auth/register", json={"email": email, "password": password}
    )
    assert created.status_code == 201
    uid = UUID(created.json()["data"]["id"])
    login = await system.http.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
    bad = await system.http.request(
        "DELETE",
        "/api/v1/users/me",
        headers=headers,
        json={"confirmation": "DELETE_ACCOUNT", "password": password + suffix},
    )
    assert bad.status_code == 422
    async with system.db() as db:
        assert await db.get(User, uid) is not None
    good = await system.http.request(
        "DELETE",
        "/api/v1/users/me",
        headers=headers,
        json={"confirmation": "DELETE_ACCOUNT", "password": password},
    )
    assert good.status_code == 204


@pytest.mark.asyncio
async def test_explicit_and_unchanged_provider_models_are_preserved_by_patch_and_sync(
    system,
) -> None:
    account = await system.account()
    for provider, model in [
        ("openai", "custom-openai-model"),
        ("claude", "custom-claude-model"),
    ]:
        current = (
            await system.http.get(
                "/api/v1/users/me/settings", headers=account["headers"]
            )
        ).json()["data"]
        values = dict(
            version=current["version"], default_provider=provider, default_model=model
        )
        patched = await system.http.patch(
            "/api/v1/users/me/settings", headers=account["headers"], json=values
        )
        assert (
            patched.status_code == 200
            and patched.json()["data"]["default_model"] == model
        )
        current = patched.json()["data"]
        synced = await system.http.post(
            "/api/v1/sync/push",
            headers=account["headers"],
            json={
                "mutations": [
                    dict(
                        entity_type="settings",
                        entity_id=current["id"],
                        action="update",
                        base_version=current["version"],
                        payload={"default_provider": provider},
                    )
                ]
            },
        )
        assert synced.status_code == 200
        current = (
            await system.http.get(
                "/api/v1/users/me/settings", headers=account["headers"]
            )
        ).json()["data"]
        assert current["default_model"] == model


@pytest.mark.asyncio
async def test_real_public_auth_ip_window_cannot_be_bypassed_with_other_tokens(
    system, monkeypatch
) -> None:
    import hashlib
    import ipaddress
    import time
    from copy import copy
    from types import SimpleNamespace

    import httpx

    from app.core import limiter, middleware
    from app.core.config import get_settings
    from app.main import app

    first, second = await system.account(), await system.account()
    address = str(ipaddress.IPv6Address(uuid4().int))
    timestamp = int(time.time())
    monkeypatch.setattr(limiter, "time", SimpleNamespace(time=lambda: timestamp))
    monkeypatch.setattr(
        middleware,
        "get_settings",
        lambda: get_settings().model_copy(update={"auth_requests_per_minute": 1}),
    )
    application = copy(app)
    application.middleware_stack = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, client=(address, 12345)),
        base_url="http://test",
    ) as client:
        statuses = []
        for headers in [first["headers"], {}, second["headers"]]:
            response = await client.post("/api/v1/auth/login", headers=headers, json={})
            statuses.append(response.status_code)
    assert statuses == [422, 429, 429]
    key = f"rate:auth:{hashlib.sha256(address.encode()).hexdigest()}:{timestamp // 60}"
    assert await system.cache.get(key) == "3"
