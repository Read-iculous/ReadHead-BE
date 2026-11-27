"""Send-side disconnects and input bypasses against real storage and ASGI calls."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import anyio
import pytest
from sqlalchemy import func, select
from starlette.requests import ClientDisconnect
from starlette.responses import StreamingResponse

from app.core.auth import Principal
from app.core.security import decode_token
from app.models.conversation import Conversation, Message
from app.models.reading_history import ReadingHistory
from app.models.user import User
from app.routers import ai as ai_router
from app.schemas.ai import AiStreamRequest
from app.services import auth_service, user_service
from tests.integration.provider_wire import ProviderWire
from tests.integration.test_ai_quiz_oauth_admin import SOURCE, store_key


@pytest.mark.asyncio
@pytest.mark.parametrize("version", ["2.3", "2.4"])
@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("disconnect_at", ["headers", "start", "token", "done"])
async def test_response_owns_cleanup_when_disconnect_happens_inside_send(
    system: SimpleNamespace,
    wire: ProviderWire,
    version: str,
    private: bool,
    disconnect_at: str,
) -> None:
    """Use the actual route response, provider SDK, SQL persistence and Redis lease."""
    account = await system.account()
    await store_key(system, account, "openai")
    if private:
        assert (
            await system.http.patch(
                "/api/v1/users/me/settings",
                headers=account["headers"],
                json={"version": 1, "privacy_mode_enabled": True},
            )
        ).status_code == 200
    claims = decode_token(account["tokens"]["access_token"], "access")
    principal = Principal(UUID(account["id"]), UUID(claims["sid"]), "user")
    response = await ai_router.stream(
        AiStreamRequest(
            task="explain",
            page_url="https://example.com/source",
            page_content=SOURCE,
            provider="openai",
            model="test-model",
        ),
        principal,
    )
    assert isinstance(response, StreamingResponse)
    disconnected = anyio.Event()
    emitted = []

    async def receive():
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def interrupt_send() -> None:
        disconnected.set()
        if version == "2.4":
            raise OSError("Synthetic client socket closed during send")
        await anyio.sleep_forever()  # Cancellation lands in send, not the generator.

    async def send(message):
        if message["type"] == "http.response.start":
            if disconnect_at == "headers":
                await interrupt_send()
            return
        if message["type"] == "http.response.body":
            body = message.get("body", b"").decode()
            emitted.append(body)
            if body.startswith(f"event: {disconnect_at}"):
                await interrupt_send()

    scope = {"type": "http", "asgi": {"spec_version": version}}
    with anyio.fail_after(10):
        if version == "2.4":
            with pytest.raises(ClientDisconnect):
                await response(scope, receive, send)
        else:
            await response(scope, receive, send)
    async with system.db() as db:
        messages = (
            await db.scalars(
                select(Message)
                .join(Conversation)
                .where(
                    Conversation.user_id == UUID(account["id"]),
                    Message.sender_role == "assistant",
                )
            )
        ).all()
        expected = 0 if private or disconnect_at in {"headers", "start"} else 1
        assert len(messages) == expected
        if messages:
            if disconnect_at == "token":
                assert messages[0].grounding_notes == "interrupted_by_client"
                assert messages[0].uncertainty_flag
            else:
                assert messages[0].grounding_notes != "interrupted_by_client"
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0
    assert not [
        key
        async for key in system.cache.scan_iter(
            f"conversation_stream:{account['id']}:*"
        )
    ]
    if disconnect_at not in {"headers", "start"}:
        assert wire.closed > 0
    if disconnect_at != "done":
        assert not any(body.startswith("event: done") for body in emitted)
    assert response.body_iterator.ag_frame is None


@pytest.mark.asyncio
@pytest.mark.parametrize("dot", ["\u3002", "\uff0e", "\uff61"])
async def test_unicode_trailing_dot_cannot_bypass_history_or_ai_blacklist(
    system: SimpleNamespace,
    wire: ProviderWire,
    dot: str,
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    patched = await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json={"version": 1, "blacklisted_domains": ["bank.com"]},
    )
    assert patched.status_code == 200
    url = f"https://bank.com{dot}/statement"
    history = await system.http.post(
        "/api/v1/reading/history", headers=account["headers"], json={"page_url": url}
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
    assert ai.status_code == 400 and ai.json()["code"] == "DOMAIN_BLOCKED_BY_PRIVACY"
    assert not any(call["method"] == "POST" for call in wire.calls)
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(ReadingHistory)
                .where(ReadingHistory.user_id == UUID(account["id"]))
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["register", "login", "delete"])
async def test_nul_password_is_rejected_before_hash_or_verify(
    system: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    from unittest.mock import MagicMock

    account = await system.account()
    spy = MagicMock(side_effect=AssertionError("Unsupported password reached bcrypt"))
    target = user_service if endpoint == "delete" else auth_service
    monkeypatch.setattr(
        target, "hash_password" if endpoint == "register" else "verify_password", spy
    )
    password = "abcd\x00efgh"
    if endpoint == "register":
        email = f"nul-check-{uuid4().hex}@example.com"
        system.emails.append(email)
        response = await system.http.post(
            "/api/v1/auth/register", json={"email": email, "password": password}
        )
    elif endpoint == "login":
        response = await system.http.post(
            "/api/v1/auth/login", json={"email": account["email"], "password": password}
        )
    else:
        response = await system.http.request(
            "DELETE",
            "/api/v1/users/me",
            headers=account["headers"],
            json={"confirmation": "DELETE_ACCOUNT", "password": password},
        )
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] == "password"
    assert password not in response.text
    spy.assert_not_called()
    async with system.db() as db:
        assert await db.get(User, UUID(account["id"])) is not None
