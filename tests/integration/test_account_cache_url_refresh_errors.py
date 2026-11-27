"""Real-storage regressions for deletion, URL indexes and error contracts."""

import asyncio
import json
import random
import string
from uuid import UUID

import pytest

from app.models.user import User
from tests.integration.test_ai_quiz_oauth_admin import (
    QUIZ,
    SOURCE,
    generate_quiz,
    store_key,
)


async def delete_account(system, account):
    return await system.http.request(
        "DELETE",
        "/api/v1/users/me",
        headers=account["headers"],
        json={"confirmation": "DELETE_ACCOUNT", "password": account["password"]},
    )


@pytest.mark.asyncio
async def test_delete_removes_owned_private_quizzes_and_preserves_other_user(
    system, wire
):
    owner, other = await system.account(), await system.account()
    qid = await generate_quiz(system, wire, owner, private=True)
    other_qid = await generate_quiz(system, wire, other, private=True)
    # An old application version did not index quizzes; deletion must handle that data too.
    legacy_key = "ephemeral_quiz:legacy-" + owner["id"]
    await system.cache.set(
        legacy_key,
        json.dumps(dict(user_id=owner["id"], questions=QUIZ["questions"])),
        ex=1800,
    )
    response = await delete_account(system, owner)
    assert response.status_code == 204
    assert not await system.cache.exists(f"ephemeral_quiz:{qid}", legacy_key)
    assert not await system.cache.exists(f"ephemeral_quiz_keys:{owner['id']}")
    assert await system.cache.exists(f"ephemeral_quiz:{other_qid}")
    async with system.db() as db:
        assert await db.get(User, UUID(owner["id"])) is None
    assert (await delete_account(system, other)).status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [True, False])
async def test_quiz_finishing_after_deletion_cannot_recreate_content(
    system, wire, private
):
    account = await system.account()
    await store_key(system, account, "openai")
    updated = await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json=dict(
            version=1,
            default_provider="openai",
            default_model="test-model",
            privacy_mode_enabled=private,
        ),
    )
    assert updated.status_code == 200
    wire.output = json.dumps(QUIZ)
    started, resume = asyncio.Event(), asyncio.Event()

    async def pause(index):
        if index == 0:
            started.set()
            await asyncio.wait_for(resume.wait(), 10)

    wire.before_chunk = pause
    task = asyncio.create_task(
        system.http.post(
            "/api/v1/quiz/generate",
            headers=account["headers"],
            json=dict(page_url="https://example.com", page_text=SOURCE),
        )
    )
    try:
        await asyncio.wait_for(started.wait(), 10)
        assert (await delete_account(system, account)).status_code == 204
    finally:
        resume.set()
    response = await asyncio.wait_for(task, 10)
    assert response.status_code == 401
    async for key in system.cache.scan_iter(match="ephemeral_quiz:*"):
        assert json.loads(await system.cache.get(key))["user_id"] != account["id"]


@pytest.mark.asyncio
async def test_long_valid_highlight_url_stores_filters_and_isolates_owner(system):
    account, other = await system.account(), await system.account()
    rng = random.Random(7021)
    # Incompressible valid URL: repeated 'a' would hide the PostgreSQL index limit.
    url = "https://example.com/" + "".join(
        rng.choices(string.ascii_letters + string.digits, k=8172)
    )
    assert len(url) == 8192
    created = await system.http.post(
        "/api/v1/reading/highlights",
        headers=account["headers"],
        json=dict(page_url=url, highlighted_text="Valid long URL"),
    )
    assert created.status_code == 201
    for user, query, count in [
        (account, url, 1),
        (account, url[:-1] + "!", 0),
        (other, url, 0),
    ]:
        result = await system.http.get(
            "/api/v1/reading/highlights",
            headers=user["headers"],
            params={"page_url": query},
        )
        assert result.status_code == 200
        assert len(result.json()["data"]["items"]) == count


@pytest.mark.asyncio
async def test_refresh_follows_more_than_ten_live_successors(system):
    account = await system.account()
    original = token = account["tokens"]["refresh_token"]
    for _ in range(12):
        response = await system.http.post(
            "/api/v1/auth/refresh", json={"refresh_token": token}
        )
        assert response.status_code == 200
        token = response.json()["data"]["refresh_token"]
    replay = await system.http.post(
        "/api/v1/auth/refresh", json={"refresh_token": original}
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["refresh_token"] == token


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "envelope",
    [
        {},
        {"mutations": None},
        {"mutations": {}},
        {"mutations": []},
        {"mutations": "bad"},
    ],
)
async def test_sync_envelope_errors_remain_422(system, envelope):
    account = await system.account()
    response = await system.http.post(
        "/api/v1/sync/push", headers=account["headers"], json=envelope
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body", [b'{"email":"\xff"}', b'{"email":"\xc0\xaf"}', b'{"email":']
)
async def test_invalid_json_bytes_have_json_error_and_cors(system, body):
    response = await system.http.post(
        "/api/v1/auth/register",
        content=body,
        headers={"Content-Type": "application/json", "Origin": "http://localhost:3000"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_JSON"
    assert response.json()["field"] is None
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["x-request-id"]
    assert "email" not in response.text


@pytest.mark.asyncio
async def test_deletion_waits_for_quiz_publication_then_removes_it(
    system, wire, monkeypatch
):
    from app.core import redis

    account = await system.account()
    await store_key(system, account, "openai")
    assert (
        await system.http.patch(
            "/api/v1/users/me/settings",
            headers=account["headers"],
            json=dict(
                version=1,
                default_provider="openai",
                default_model="test-model",
                privacy_mode_enabled=True,
            ),
        )
    ).status_code == 200
    wire.output = json.dumps(QUIZ)
    saved, resume = asyncio.Event(), asyncio.Event()
    original = redis.cache_private_quiz

    async def pause(*args):
        result = await original(*args)
        saved.set()
        await asyncio.wait_for(resume.wait(), 10)
        return result

    monkeypatch.setattr(redis, "cache_private_quiz", pause)
    generation = asyncio.create_task(
        system.http.post(
            "/api/v1/quiz/generate",
            headers=account["headers"],
            json=dict(page_url="https://example.com", page_text=SOURCE),
        )
    )
    deletion = None
    try:
        await asyncio.wait_for(saved.wait(), 10)
        deletion = asyncio.create_task(delete_account(system, account))
        await asyncio.sleep(0.15)
        assert not deletion.done()
    finally:
        resume.set()
    generated = await asyncio.wait_for(generation, 10)
    assert generated.status_code == 200
    assert (await asyncio.wait_for(deletion, 10)).status_code == 204
    assert not await system.cache.exists(
        "ephemeral_quiz:" + generated.json()["data"]["quiz_id"]
    )


@pytest.mark.asyncio
async def test_deletion_does_not_report_success_when_cache_cleanup_fails(
    system, wire, monkeypatch
):
    from unittest.mock import AsyncMock

    from redis.exceptions import ConnectionError

    account = await system.account()
    qid = await generate_quiz(system, wire, account, private=True)
    with monkeypatch.context() as patch:
        patch.setattr(
            system.cache,
            "smembers",
            AsyncMock(side_effect=ConnectionError("injected cleanup failure")),
        )
        response = await delete_account(system, account)
    assert response.status_code == 503 and response.json()["code"] == "SERVICE_DEGRADED"
    async with system.db() as db:
        assert await db.get(User, UUID(account["id"])) is not None
    assert await system.cache.exists(f"ephemeral_quiz:{qid}")
    assert (await delete_account(system, account)).status_code == 204
    assert not await system.cache.exists(f"ephemeral_quiz:{qid}")
