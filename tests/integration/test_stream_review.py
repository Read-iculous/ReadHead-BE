"""Streaming regressions: real auth/storage/leases and synthetic provider frames."""

import json
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.auth import Principal
from app.core.security import decode_token
from app.models.auth_session import AuthSession
from app.models.conversation import Message
from app.models.quiz import QuizRecord
from app.schemas.ai import AiStreamRequest
from app.services import ai_service
from tests.integration.provider_wire import ProviderWire
from tests.integration.test_ai_quiz_oauth_admin import (
    QUIZ,
    SOURCE,
    sse_events,
    store_key,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_before_chunk", [1, 2])
async def test_reactivation_does_not_restore_an_already_revoked_stream(
    system: SimpleNamespace, wire: ProviderWire, revoke_before_chunk: int
) -> None:
    admin, account = await system.account(admin=True), await system.account()
    await store_key(system, account, "openai")
    sid = decode_token(account["tokens"]["access_token"], "access")["sid"]

    async def suspend_and_reactivate(index: int) -> None:
        if index == revoke_before_chunk:
            for status in ["suspended", "active"]:
                response = await system.http.patch(
                    f"/api/v1/admin/users/{account['id']}/status",
                    headers=admin["headers"],
                    json={"status": status},
                )
                assert response.status_code == 200

    wire.before_chunk = suspend_and_reactivate
    payload = dict(
        task="explain",
        page_url="https://example.com/source",
        page_content=SOURCE,
        provider="openai",
        model="test-model",
    )
    streamed = await system.http.post(
        "/api/v1/ai/stream", headers=account["headers"], json=payload
    )
    events = sse_events(streamed)
    assert [name for name, _ in events] == [
        "start",
        *(["token"] * revoke_before_chunk),
        "error",
    ]
    assert events[-1][1]["code"] == "UNAUTHORIZED"
    async with system.db() as db:
        assert (await db.get(AuthSession, UUID(sid))).revoked_at is not None
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .where(
                    Message.conversation_id == UUID(events[0][1]["conversation_id"]),
                    Message.sender_role == "assistant",
                )
            )
            == 0
        )
    assert await system.cache.exists(f"revoked_sessions:{sid}")
    assert not await system.cache.exists(f"revoked_users:{account['id']}")
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0
    wire.before_chunk = None
    login = await system.http.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
    assert (
        sse_events(
            await system.http.post("/api/v1/ai/stream", headers=headers, json=payload)
        )[-1][0]
        == "done"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sensitive", [False, True])
async def test_history_is_refreshed_after_previous_stream_commits_before_admission(
    system: SimpleNamespace,
    wire: ProviderWire,
    monkeypatch: pytest.MonkeyPatch,
    sensitive: bool,
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    claims = decode_token(account["tokens"]["access_token"], "access")
    principal = Principal(UUID(account["id"]), UUID(claims["sid"]), "user")
    reading_session = str(uuid4())
    payload = dict(
        task="chat",
        page_url="https://example.com/source",
        page_content=SOURCE,
        provider="openai",
        model="test-model",
        reading_session_id=reading_session,
        user_prompt="First question",
    )
    previous = await ai_service.prepare(principal, AiStreamRequest(**payload))
    latest_answer = "A previous answer committed just before admission [p-1]."
    if sensitive:
        latest_answer += " Contact private-reader@example.com."
    original = ai_service.active_key

    async def finish_previous(db, uid, provider):
        key = await original(db, uid, provider)
        # Explicit previous-response fixture, stored by the actual persistence service.
        await ai_service.persist(
            principal,
            previous,
            latest_answer,
            dict(
                is_grounded=True,
                uncertainty_flag=False,
                grounding_notes="Synthetic regression fixture",
            ),
        )
        await previous.lease.close()
        return key

    monkeypatch.setattr(ai_service, "active_key", finish_previous)
    try:
        response = await system.http.post(
            "/api/v1/ai/stream",
            headers=account["headers"],
            json={
                **payload,
                "conversation_id": str(previous.cid),
                "user_prompt": "Next question",
            },
        )
        if sensitive:
            assert (
                response.status_code == 400
                and response.json()["code"] == "SENSITIVE_DATA_DETECTED"
            )
            assert not any(call["method"] == "POST" for call in wire.calls)
        else:
            assert response.status_code == 200 and sse_events(response)[-1][0] == "done"
            sent = wire.calls[-1]["body"]["messages"]
            assert any(
                turn["role"] == "assistant" and turn["content"] == latest_answer
                for turn in sent
            )
    finally:
        await previous.lease.close()
        previous.provider.key = ""


@pytest.mark.asyncio
async def test_session_marker_outlives_max_stream_even_with_short_access_tokens(
    system: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core import redis
    from app.core.config import get_settings

    settings = get_settings().model_copy(update={"access_token_expire_minutes": 1})
    monkeypatch.setattr(redis, "get_settings", lambda: settings)
    sid = str(uuid4())
    await redis.mark_session_revoked(sid)
    assert 239 <= await system.cache.ttl(f"revoked_sessions:{sid}") <= 240


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "claude", "gemini"])
@pytest.mark.parametrize("private", [False, True])
async def test_output_limit_is_reported_and_saved_as_incomplete(
    system: SimpleNamespace, wire: ProviderWire, provider: str, private: bool
) -> None:
    account = await system.account()
    await store_key(system, account, provider)
    if private:
        assert (
            await system.http.patch(
                "/api/v1/users/me/settings",
                headers=account["headers"],
                json={"version": 1, "privacy_mode_enabled": True},
            )
        ).status_code == 200
    wire.finish_reason = "length"
    response = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="translate",
            page_url="https://example.com/source",
            page_content=SOURCE,
            provider=provider,
            model="test-model",
        ),
    )
    events = sse_events(response)
    name, done = events[-1]
    assert name == "done" and done["finish_reason"] == "length"
    assert done["uncertainty_flag"] is True and done["is_grounded"] is False
    assert "truncat" in done["grounding_notes"]
    async with system.db() as db:
        row = await db.get(Message, UUID(done["message_id"]))
        if private:
            assert row is None
        else:
            assert (
                row.content == wire.output
                and row.uncertainty_flag
                and not row.is_grounded
            )
            assert "truncat" in row.grounding_notes


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "claude", "gemini"])
@pytest.mark.parametrize("operation", ["quiz", "proactive"])
async def test_nonstream_operations_reject_provider_truncation(
    system: SimpleNamespace, wire: ProviderWire, provider: str, operation: str
) -> None:
    account = await system.account()
    await store_key(system, account, provider)
    assert (
        await system.http.patch(
            "/api/v1/users/me/settings",
            headers=account["headers"],
            json=dict(version=1, default_provider=provider, default_model="test-model"),
        )
    ).status_code == 200
    wire.finish_reason = "length"
    if operation == "quiz":
        wire.output = json.dumps(QUIZ)  # Even valid JSON is not a complete generation.
        path, payload = "/api/v1/quiz/generate", dict(
            page_url="https://example.com/source", page_text=SOURCE
        )
    else:
        path, payload = "/api/v1/ai/proactive-suggest", dict(
            page_url="https://example.com/source",
            paragraph_text=SOURCE,
            dwell_time_seconds=30,
        )
    response = await system.http.post(path, headers=account["headers"], json=payload)
    assert (
        response.status_code == 502 and response.json()["code"] == "UPSTREAM_AI_ERROR"
    )
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(QuizRecord)
                .where(QuizRecord.user_id == UUID(account["id"]))
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "claude", "gemini"])
async def test_missing_provider_finish_is_not_reported_as_a_complete_response(
    system: SimpleNamespace, wire: ProviderWire, provider: str
) -> None:
    account = await system.account()
    await store_key(system, account, provider)
    wire.finish_reason = None
    response = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="explain",
            page_url="https://example.com/source",
            page_content=SOURCE,
            provider=provider,
            model="test-model",
        ),
    )
    events = sse_events(response)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "UPSTREAM_AI_ERROR"
    assert not any(name == "done" for name, _ in events)
