"""Marker publication ordering and non-stream completion validation regressions."""

import asyncio
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy import func, select, text

from app.core import redis
from app.models.quiz import QuizRecord
from app.models.user import User
from tests.integration.provider_wire import ProviderWire
from tests.integration.test_ai_quiz_oauth_admin import SOURCE, sse_events, store_key


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_status", "second_status"),
    [("suspended", "active"), ("active", "suspended")],
)
async def test_marker_publication_cannot_reverse_status_commit_order(
    system: SimpleNamespace,
    wire: ProviderWire,
    monkeypatch: pytest.MonkeyPatch,
    first_status: str,
    second_status: str,
) -> None:
    """Pause the first Redis publish; let the next writer finish or block on SQL."""
    admin, account = await system.account(admin=True), await system.account()
    await store_key(system, account, "openai")
    path = f"/api/v1/admin/users/{account['id']}/status"
    if first_status == "active":
        initial = await system.http.patch(
            path, headers=admin["headers"], json={"status": "suspended"}
        )
        assert initial.status_code == 200
    key = f"revoked_users:{account['id']}"
    reached, release = asyncio.Event(), asyncio.Event()
    mark, delete = redis.mark, system.cache.delete
    gated = False

    async def barrier() -> None:
        nonlocal gated
        if not gated:
            gated = True
            reached.set()
            await release.wait()

    async def delayed_mark(name: str, ttl: int = 3600) -> None:
        if name == key:
            await barrier()
        await mark(name, ttl)

    async def delayed_delete(*keys):
        if key in keys:
            await barrier()
        return await delete(*keys)

    monkeypatch.setattr(redis, "mark", delayed_mark)
    monkeypatch.setattr(system.cache, "delete", delayed_delete)
    first = asyncio.create_task(
        system.http.patch(path, headers=admin["headers"], json={"status": first_status})
    )
    second = None
    try:
        await asyncio.wait_for(reached.wait(), timeout=10)
        second = asyncio.create_task(
            system.http.patch(
                path, headers=admin["headers"], json={"status": second_status}
            )
        )

        async def wait_for_second() -> None:
            while not second.done():
                async with system.db() as db:
                    blocked = await db.scalar(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND cardinality(pg_blocking_pids(pid)) > 0)"
                        )
                    )
                if blocked:
                    return
                await asyncio.sleep(0.02)

        await asyncio.wait_for(wait_for_second(), timeout=10)
    finally:
        release.set()
        tasks = [first] + ([second] if second else [])
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)
    assert all(response.status_code == 200 for response in responses)
    async with system.db() as db:
        user = await db.get(User, UUID(account["id"]))
        assert user.status == second_status
    assert bool(await system.cache.exists(key)) == (second_status != "active")
    login = await system.http.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    if second_status == "active":
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
        stream = await system.http.post(
            "/api/v1/ai/stream",
            headers=headers,
            json=dict(
                task="explain",
                page_url="https://example.com/source",
                page_content=SOURCE,
                provider="openai",
                model="test-model",
            ),
        )
        assert sse_events(stream)[-1][0] == "done"
    else:
        assert login.status_code == 401 and login.json()["code"] == "USER_SUSPENDED"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "claude", "gemini"])
@pytest.mark.parametrize("output", ["", " \n\t "])
@pytest.mark.parametrize("operation", ["proactive", "quiz"])
async def test_empty_normal_stop_is_not_a_successful_completion(
    system: SimpleNamespace,
    wire: ProviderWire,
    provider: str,
    output: str,
    operation: str,
) -> None:
    """Actual SDK receives a normal terminal frame without usable text."""
    account = await system.account()
    await store_key(system, account, provider)
    changed = await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json=dict(version=1, default_provider=provider, default_model="test-model"),
    )
    assert changed.status_code == 200
    wire.output, wire.finish_reason = output, "stop"
    if operation == "proactive":
        path, body = "/api/v1/ai/proactive-suggest", dict(
            page_url="https://example.com/source",
            paragraph_text=SOURCE,
            dwell_time_seconds=30,
        )
    else:
        path, body = "/api/v1/quiz/generate", dict(
            page_url="https://example.com/source", page_text=SOURCE
        )
    response = await system.http.post(path, headers=account["headers"], json=body)
    assert (
        response.status_code == 502 and response.json()["code"] == "UPSTREAM_AI_ERROR"
    )
    assert "has_suggestion" not in response.json()
    assert sum(call["method"] == "POST" for call in wire.calls) == 1
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(QuizRecord)
                .where(QuizRecord.user_id == UUID(account["id"]))
            )
            == 0
        )
