"""Real local storage/auth integration; all external upstream responses are mocked."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import httpx
import pytest
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core import middleware
from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models.api_key import UserApiKey
from app.models.auth_session import AuthSession
from app.models.conversation import Conversation, Message
from app.models.feedback import AiFeedback
from app.models.quiz import QuizRecord
from app.models.refresh_token import RefreshToken
from app.models.user import OAuthAccount, User
from tests.integration.provider_wire import ProviderWire

SOURCE = "Reading source material explains how plants convert sunlight into stored energy. Leaves collect light and water supports the process. The resulting sugars provide energy for growth and oxygen is released into the air."
QUIZ = {
    "questions": [
        dict(
            question_id=i,
            question_text=f"Source question {i}?",
            options=["A", "B", "C", "D"],
            correct_option=i - 1,
            explanation="Supported by the supplied source.",
        )
        for i in range(1, 4)
    ]
}


def sse_events(response) -> list[tuple[str, dict]]:
    """Parse observed public SSE frames rather than calling service internals."""
    return [
        (block.splitlines()[0][7:], json.loads(block.splitlines()[1][6:]))
        for block in response.text.strip().split("\n\n")
    ]


async def store_key(system: SimpleNamespace, account: dict, provider: str) -> str:
    """Exercise the real key vault against mocked provider authentication HTTP."""
    key = f"approved-test-{provider}-credential"
    response = await system.http.post(
        "/api/v1/api-keys",
        headers=account["headers"],
        json=dict(provider=provider, api_key=key),
    )
    assert response.status_code == 201
    async with system.db() as db:
        row = await db.scalar(
            select(UserApiKey).where(
                UserApiKey.user_id == UUID(account["id"]),
                UserApiKey.provider == provider,
            )
        )
        assert row.encrypted_key.startswith("v1:")
        assert key not in row.encrypted_key
        assert decrypt_secret(row.encrypted_key) == key
    assert key not in response.text
    return key


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "gemini", "claude"])
@pytest.mark.parametrize(
    "task", ["explain", "summarize", "translate", "simplify", "chat"]
)
async def test_provider_sdk_vault_sse_commit_and_key_replacement(
    system, wire: ProviderWire, provider: str, task: str
) -> None:
    account = await system.account()
    key = await store_key(system, account, provider)
    validated = await system.http.post(
        f"/api/v1/api-keys/{provider}/validate", headers=account["headers"]
    )
    assert validated.status_code == 200
    rejected = await system.http.post(
        "/api/v1/api-keys",
        headers=account["headers"],
        json=dict(provider=provider, api_key="rejected-test-key-credential"),
    )
    assert rejected.status_code == 400
    async with system.db() as db:
        cipher = await db.scalar(
            select(UserApiKey.encrypted_key).where(
                UserApiKey.user_id == UUID(account["id"])
            )
        )
        assert decrypt_secret(cipher) == key
    session = str(uuid4())
    payload = dict(
        task=task,
        page_url="https://example.com/source",
        page_content=SOURCE,
        reading_session_id=session,
        provider=provider,
        model="test-model",
    )
    response = await system.http.post(
        "/api/v1/ai/stream", headers=account["headers"], json=payload
    )
    assert response.status_code == 200
    events = sse_events(response)
    assert [name for name, _ in events] == [
        "start",
        "token",
        "token",
        "citation",
        "done",
    ]
    cid = UUID(events[0][1]["conversation_id"])
    mid = UUID(events[-1][1]["message_id"])
    async with system.db() as db:
        saved = await db.get(Message, mid)
        conv = await db.get(Conversation, cid)
        assert saved.content == wire.output and saved.provider_used == provider
        assert conv.version == 3 and conv.reading_session_id == UUID(session)
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0
    assert await system.cache.exists(f"conversation_stream:{account['id']}:{cid}") == 0
    assert wire.closed > 0
    unbound = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json={**payload, "conversation_id": str(cid), "reading_session_id": None},
    )
    assert (
        unbound.status_code == 400 and unbound.json()["code"] == "TAB_CONTEXT_MISMATCH"
    )
    deleted = await system.http.delete(
        f"/api/v1/api-keys/{provider}", headers=account["headers"]
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "timeout", "code"),
    [
        (429, False, "UPSTREAM_QUOTA_EXCEEDED"),
        (500, False, "UPSTREAM_AI_ERROR"),
        (200, True, "UPSTREAM_AI_TIMEOUT"),
    ],
)
async def test_upstream_errors_end_sse_without_done_or_assistant_commit(
    system, wire, status, timeout, code
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    wire.status, wire.timeout = status, timeout
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
    assert [name for name, _ in events] == ["start", "error"]
    assert events[-1][1]["code"] == code
    async with system.db() as db:
        roles = (
            await db.scalars(
                select(Message.sender_role).where(
                    Message.conversation_id == UUID(events[0][1]["conversation_id"])
                )
            )
        ).all()
        assert roles == ["user"]
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0


@pytest.mark.asyncio
async def test_private_ai_proactive_and_sensitive_policy_have_no_history_writes(
    system, wire
) -> None:
    account = await system.account()
    await store_key(system, account, "gemini")
    await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json=dict(version=1, privacy_mode_enabled=True),
    )
    response = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="summarize",
            page_url="https://example.com/source",
            page_content=SOURCE,
            ephemeral_history=[
                dict(role="assistant", content="A previous private response")
            ],
        ),
    )
    assert sse_events(response)[-1][0] == "done"
    assert wire.calls[-1]["body"]["contents"][0]["role"] == "user"
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Conversation)
                .where(Conversation.user_id == UUID(account["id"]))
            )
            == 0
        )
    calls = len(wire.calls)
    blocked = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="explain",
            page_url="https://example.com/source",
            selected_text="Contact personal@example.com",
        ),
    )
    assert (
        blocked.status_code == 400
        and blocked.json()["code"] == "SENSITIVE_DATA_DETECTED"
    )
    assert len(wire.calls) == calls
    early = await system.http.post(
        "/api/v1/ai/proactive-suggest",
        headers=account["headers"],
        json=dict(
            page_url="https://example.com/source",
            paragraph_text=SOURCE,
            dwell_time_seconds=1,
        ),
    )
    assert early.json()["data"]["has_suggestion"] is False and len(wire.calls) == calls
    hint = await system.http.post(
        "/api/v1/ai/proactive-suggest",
        headers=account["headers"],
        json=dict(
            page_url="https://example.com/source",
            paragraph_text=SOURCE,
            dwell_time_seconds=30,
        ),
    )
    assert hint.status_code == 200 and hint.json()["data"]["has_suggestion"]


async def generate_quiz(system, wire, account, private=False) -> str:
    """Set up a generated quiz through real provider SDK and HTTP boundary."""
    await store_key(system, account, "openai")
    settings = dict(
        version=1,
        default_provider="openai",
        default_model="test-model",
        privacy_mode_enabled=private,
    )
    assert (
        await system.http.patch(
            "/api/v1/users/me/settings", headers=account["headers"], json=settings
        )
    ).status_code == 200
    wire.output = json.dumps(QUIZ)
    response = await system.http.post(
        "/api/v1/quiz/generate",
        headers=account["headers"],
        json=dict(page_url="https://example.com/source", page_text=SOURCE),
    )
    assert response.status_code == 200
    assert all(
        "correct_option" not in question and "explanation" not in question
        for question in response.json()["data"]["questions"]
    )
    return response.json()["data"]["quiz_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
async def test_quiz_owner_isolation_atomic_single_grading_and_privacy(
    system, wire, private
) -> None:
    account, stranger = await system.account(), await system.account()
    qid = await generate_quiz(system, wire, account, private)
    async with system.db() as db:
        persisted = await db.get(QuizRecord, UUID(qid))
        assert (persisted is None) == private
    if private:
        assert 0 < await system.cache.ttl(f"ephemeral_quiz:{qid}") <= 1800
    other = await system.http.post(
        f"/api/v1/quiz/{qid}/submit",
        headers=stranger["headers"],
        json={"answers": {"1": 0, "2": 1, "3": 2}},
    )
    assert other.status_code == 404
    invalid = await system.http.post(
        f"/api/v1/quiz/{qid}/submit",
        headers=account["headers"],
        json={"answers": {"1": 0}},
    )
    assert invalid.status_code == 422
    responses = await asyncio.gather(
        *(
            system.http.post(
                f"/api/v1/quiz/{qid}/submit",
                headers=account["headers"],
                json={"answers": {"1": 0, "2": 1, "3": 2}},
            )
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 400]
    success = next(r for r in responses if r.status_code == 200).json()["data"]
    assert success["score"] == success["total"] == 3
    if not private:
        async with system.db() as db:
            row = await db.get(QuizRecord, UUID(qid))
            assert row.score == 3 and row.user_answers == {"1": 0, "2": 1, "3": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [True, "1", 1.0])
async def test_quiz_rejects_non_integer_answer_at_http_boundary(
    system, wire, answer
) -> None:
    account = await system.account()
    qid = await generate_quiz(system, wire, account)
    response = await system.http.post(
        f"/api/v1/quiz/{qid}/submit",
        headers=account["headers"],
        json={"answers": {"1": 0, "2": answer, "3": 2}},
    )
    assert response.status_code == 422
    async with system.db() as db:
        assert (await db.get(QuizRecord, UUID(qid))).score is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "github"])
async def test_oauth_new_account_linking_repeat_login_and_suspension(
    system, wire, provider
) -> None:
    email = f"oauth-{uuid4().hex}@example.com"
    system.emails.append(email)
    if provider == "google":
        wire.google.update(email=email, sub=uuid4().hex)
    else:
        wire.github_emails[0]["email"] = email
        wire.github_profile["id"] = uuid4().int % (10**12) + 1
    payload = {
        "id_token" if provider == "google" else "code": "synthetic-identity-token"
    }
    first = await system.http.post(f"/api/v1/auth/oauth/{provider}", json=payload)
    assert first.status_code == 200
    second = await system.http.post(f"/api/v1/auth/oauth/{provider}", json=payload)
    assert second.status_code == 200
    async with system.db.begin() as db:
        user = await db.scalar(select(User).where(User.email == email))
        assert user.hashed_password is None and user.is_verified
        assert (
            await db.scalar(
                select(func.count())
                .select_from(OAuthAccount)
                .where(OAuthAccount.user_id == user.id)
            )
            == 1
        )
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == user.id)
            )
            == 2
        )
        user.status, user.is_active = "suspended", False
    denied = await system.http.post(f"/api/v1/auth/oauth/{provider}", json=payload)
    assert denied.status_code == 401 and denied.json()["code"] == "USER_SUSPENDED"


@pytest.mark.asyncio
async def test_oauth_verified_email_links_existing_password_account(
    system, wire
) -> None:
    account = await system.account()
    wire.google.update(email=account["email"], sub=uuid4().hex)
    response = await system.http.post(
        "/api/v1/auth/oauth/google", json={"id_token": "synthetic-id-token"}
    )
    assert response.status_code == 200
    headers = {"Authorization": "Bearer " + response.json()["data"]["access_token"]}
    profile = await system.http.get("/api/v1/users/me", headers=headers)
    assert profile.json()["data"]["id"] == account["id"]
    assert profile.json()["data"]["linked_accounts"] == ["google"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "status", "code"),
    [
        ({"aud": "wrong"}, 401, "TOKEN_INVALID"),
        ({"iss": "https://attacker.example"}, 401, "TOKEN_INVALID"),
        ({"exp": 0}, 401, "TOKEN_INVALID"),
        ({"email_verified": "false"}, 403, "EMAIL_NOT_VERIFIED"),
        ({"sub": None}, 401, "TOKEN_INVALID"),
        ({"email": 5}, 401, "TOKEN_INVALID"),
        ({"name": {}}, 401, "TOKEN_INVALID"),
    ],
)
async def test_google_invalid_identity_never_writes_account(
    system, wire, change, status, code
) -> None:
    system.emails.append(wire.google["email"])
    wire.google.update(change)
    response = await system.http.post(
        "/api/v1/auth/oauth/google", json={"id_token": "synthetic-invalid-identity"}
    )
    assert response.status_code == status
    assert response.json()["code"] == code


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["google", "github"])
async def test_oauth_malformed_provider_shape_returns_auth_error(
    system, wire, provider
) -> None:
    system.emails.extend([wire.google["email"], wire.github_emails[0]["email"]])
    if provider == "google":
        wire.google = []
    else:
        wire.github_emails = {"unexpected": "object"}
    payload = {
        "id_token" if provider == "google" else "code": "synthetic-invalid-identity"
    }
    response = await system.http.post(f"/api/v1/auth/oauth/{provider}", json=payload)
    assert response.status_code == 401 and response.json()["code"] == "TOKEN_INVALID"


@pytest.mark.asyncio
async def test_admin_moderation_filters_feedback_and_revoked_sessions(
    system, wire
) -> None:
    admin, account = await system.account(admin=True), await system.account()
    session2 = await system.http.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert session2.status_code == 200
    own = await system.http.patch(
        f"/api/v1/admin/users/{admin['id']}/status",
        headers=admin["headers"],
        json={"status": "suspended"},
    )
    assert own.status_code == 400 and own.json()["code"] == "CANNOT_MODIFY_SELF_STATUS"
    unknown = await system.http.patch(
        f"/api/v1/admin/users/{uuid4()}/status",
        headers=admin["headers"],
        json={"status": "banned"},
    )
    assert unknown.status_code == 404
    for status in ["suspended", "active", "banned", "active"]:
        changed = await system.http.patch(
            f"/api/v1/admin/users/{account['id']}/status",
            headers=admin["headers"],
            json={"status": status},
        )
        assert changed.status_code == 200
        async with system.db() as db:
            user = await db.get(User, UUID(account["id"]))
            assert user.status == status and user.is_active == (status == "active")
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuthSession)
                    .where(
                        AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)
                    )
                )
                == 0
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(RefreshToken)
                    .where(
                        RefreshToken.user_id == user.id,
                        RefreshToken.is_revoked.is_(False),
                    )
                )
                == 0
            )
        assert bool(await system.cache.exists(f"revoked_users:{account['id']}")) == (
            status != "active"
        )
        old_access = await system.http.get(
            "/api/v1/users/me", headers=account["headers"]
        )
        assert old_access.status_code == 401
        old_refresh = await system.http.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": account["tokens"]["refresh_token"]},
        )
        assert old_refresh.status_code == 401
        filtered = await system.http.get(
            "/api/v1/admin/users", headers=admin["headers"], params={"status": status}
        )
        assert filtered.status_code == 200
        assert all(
            u["status"] == status and "hashed_password" not in u
            for u in filtered.json()["data"]["items"]
        )
    fresh = await system.http.post(
        "/api/v1/auth/login",
        json={"email": account["email"], "password": account["password"]},
    )
    assert fresh.status_code == 200
    account["headers"] = {
        "Authorization": "Bearer " + fresh.json()["data"]["access_token"]
    }
    await store_key(system, account, "openai")
    streamed = await system.http.post(
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
    mid = sse_events(streamed)[-1][1]["message_id"]
    for rating in ["helpful", "unhelpful"]:
        feedback = await system.http.post(
            "/api/v1/ai/feedback",
            headers=account["headers"],
            json=dict(
                message_id=mid,
                rating=rating,
                comment="Contact reader@example.com about this issue",
            ),
        )
        assert feedback.status_code == 201
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AiFeedback)
                .where(AiFeedback.message_id == UUID(mid))
            )
            == 1
        )
    feedbacks = await system.http.get(
        "/api/v1/admin/feedback", headers=admin["headers"]
    )
    assert feedbacks.status_code == 200
    assert "reader@example.com" not in feedbacks.text and "[REDACTED]" in feedbacks.text
    for timeframe in ["24h", "7d", "30d"]:
        response = await system.http.get(
            "/api/v1/admin/telemetry",
            headers=admin["headers"],
            params={"timeframe": timeframe},
        )
        assert response.status_code == 200
        assert response.json()["data"]["provider_split"]["openai"] > 0
        assert "page_url" not in response.text and SOURCE not in response.text
    denied = await system.http.get("/api/v1/admin/users", headers=account["headers"])
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_rate_limited_responses_are_included_in_admin_telemetry(
    system, monkeypatch
) -> None:
    account = await system.account(admin=True)

    async def totals() -> tuple[int, int]:
        requests, errors = 0, 0
        async for key in system.cache.scan_iter("metrics:*"):
            values = await system.cache.hgetall(key)
            requests += int(values.get("requests", 0))
            errors += int(values.get("errors", 0))
        return requests, errors

    before = await totals()
    cfg = get_settings().model_copy(update={"auth_requests_per_minute": 1})
    monkeypatch.setattr(middleware, "get_settings", lambda: cfg)
    # A unique bearer identity keeps this rate bucket separate from other tests.
    for _ in range(2):
        response = await system.http.post(
            "/api/v1/auth/login", headers=account["headers"], json={}
        )
    assert response.status_code == 429
    after = await totals()
    assert after[0] - before[0] == 2
    assert after[1] - before[1] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["openai", "gemini", "claude"])
async def test_timeout_while_reading_provider_stream_keeps_timeout_code(
    system, wire, provider
) -> None:
    account = await system.account()
    await store_key(system, account, provider)

    async def timeout(index: int) -> None:
        if index == 1:
            raise httpx.ReadTimeout("Synthetic timeout after response headers")

    wire.before_chunk = timeout
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
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "UPSTREAM_AI_TIMEOUT"
    assert all(name != "done" for name, _ in events)


@pytest.mark.asyncio
async def test_admin_suspension_stops_inflight_ai_stream(system, wire) -> None:
    admin, account = await system.account(admin=True), await system.account()
    await store_key(system, account, "openai")

    async def suspend(index: int) -> None:
        if index == 1:
            response = await system.http.patch(
                f"/api/v1/admin/users/{account['id']}/status",
                headers=admin["headers"],
                json={"status": "banned"},
            )
            assert response.status_code == 200

    wire.before_chunk = suspend
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
    assert [name for name, _ in events] == ["start", "token", "error"]
    assert events[-1][1]["code"] == "USER_SUSPENDED"
    assert wire.closed > 0
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", ["not_json", "duplicate_ids", "boolean_answer", "string_id"]
)
async def test_malformed_generated_quiz_never_persists(system, wire, failure) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json=dict(version=1, default_provider="openai", default_model="test-model"),
    )
    quiz = json.loads(json.dumps(QUIZ))
    if failure == "duplicate_ids":
        quiz["questions"][1]["question_id"] = 1
    elif failure == "boolean_answer":
        quiz["questions"][0]["correct_option"] = True
    elif failure == "string_id":
        quiz["questions"][0]["question_id"] = "1"
    wire.output = "not JSON" if failure == "not_json" else json.dumps(quiz)
    response = await system.http.post(
        "/api/v1/quiz/generate",
        headers=account["headers"],
        json=dict(page_url="https://example.com/source", page_text=SOURCE),
    )
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
@pytest.mark.parametrize("provider", ["google", "github"])
async def test_oauth_unconfigured_is_explicit_without_upstream_call(
    system, wire, monkeypatch, provider
) -> None:
    from pydantic import SecretStr

    from app.services import auth_service

    cfg = get_settings().model_copy(
        update=dict(
            google_client_id="", github_client_id="", github_client_secret=SecretStr("")
        )
    )
    monkeypatch.setattr(auth_service, "get_settings", lambda: cfg)
    payload = {"id_token" if provider == "google" else "code": "synthetic-identity"}
    response = await system.http.post(f"/api/v1/auth/oauth/{provider}", json=payload)
    assert response.status_code == 503 and response.json()["code"] == "SERVICE_DEGRADED"
    assert not wire.calls


@pytest.mark.asyncio
async def test_github_requires_verified_primary_email_and_valid_token(
    system, wire
) -> None:
    wire.github_emails[0]["verified"] = False
    response = await system.http.post(
        "/api/v1/auth/oauth/github", json={"code": "synthetic-identity"}
    )
    assert (
        response.status_code == 400 and response.json()["code"] == "OAUTH_EMAIL_MISSING"
    )
    wire.github_token = {"error": "bad_verification_code"}
    response = await system.http.post(
        "/api/v1/auth/oauth/github", json={"code": "synthetic-invalid-code"}
    )
    assert response.status_code == 401 and response.json()["code"] == "TOKEN_INVALID"


@pytest.mark.asyncio
async def test_admin_input_bounds_and_bootstrap_cannot_elevate_existing_account(
    system,
) -> None:
    from app.cli.create_admin import create

    admin, account = await system.account(admin=True), await system.account()
    with pytest.raises(ValueError, match="already exists"):
        await create(account["email"], account["password"])
    async with system.db() as db:
        assert (await db.get(User, UUID(account["id"]))).role == "user"
    for path, params in [
        ("/api/v1/admin/users", {"page_size": 101}),
        ("/api/v1/admin/users", {"status": "invalid"}),
        ("/api/v1/admin/feedback", {"page": 0}),
        ("/api/v1/admin/telemetry", {"timeframe": "all"}),
    ]:
        response = await system.http.get(path, headers=admin["headers"], params=params)
        assert response.status_code == 422
    response = await system.http.patch(
        f"/api/v1/admin/users/{account['id']}/status",
        headers=admin["headers"],
        json={"status": "invalid"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_redis_failure_preserves_committed_revocation_and_reports_degraded_metrics(
    system, monkeypatch
) -> None:
    admin, account = await system.account(admin=True), await system.account()
    with monkeypatch.context() as fault:
        fault.setattr(
            system.cache,
            "set",
            AsyncMock(side_effect=RedisError("synthetic publish outage")),
        )
        fault.setattr(
            system.cache,
            "smembers",
            AsyncMock(side_effect=RedisError("synthetic cleanup outage")),
        )
        response = await system.http.patch(
            f"/api/v1/admin/users/{account['id']}/status",
            headers=admin["headers"],
            json={"status": "suspended"},
        )
        assert response.status_code == 200
    async with system.db() as db:
        row = await db.get(User, UUID(account["id"]))
        assert row.status == "suspended" and not row.is_active
        assert (
            await db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(AuthSession.user_id == row.id, AuthSession.revoked_at.is_(None))
            )
            == 0
        )
    denied = await system.http.get("/api/v1/users/me", headers=account["headers"])
    assert denied.status_code == 401
    with monkeypatch.context() as fault:
        fault.setattr(
            system.cache,
            "pipeline",
            MagicMock(side_effect=RedisError("synthetic telemetry outage")),
        )
        response = await system.http.get(
            "/api/v1/admin/telemetry", headers=admin["headers"]
        )
        assert (
            response.status_code == 503
            and response.json()["code"] == "SERVICE_DEGRADED"
        )


@pytest.mark.asyncio
async def test_assistant_persistence_failure_emits_error_without_done(
    system, wire, monkeypatch
) -> None:
    from app.services import ai_service

    account = await system.account()
    await store_key(system, account, "openai")
    monkeypatch.setattr(
        ai_service,
        "persist",
        AsyncMock(side_effect=SQLAlchemyError("synthetic assistant commit failure")),
    )
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
    assert events[-1][0] == "error" and events[-1][1]["code"] == "PERSISTENCE_FAILED"
    assert all(name != "done" for name, _ in events)
    async with system.db() as db:
        roles = (
            await db.scalars(
                select(Message.sender_role).where(
                    Message.conversation_id == UUID(events[0][1]["conversation_id"])
                )
            )
        ).all()
        assert roles == ["user"]
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0


@pytest.mark.asyncio
async def test_quiz_privacy_toggle_during_generation_uses_only_ephemeral_cache(
    system, wire
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json=dict(version=1, default_provider="openai", default_model="test-model"),
    )
    wire.output = json.dumps(QUIZ)

    updates = []

    async def enable_privacy(index: int) -> None:
        if index == 0:
            changed = await system.http.patch(
                "/api/v1/users/me/settings",
                headers=account["headers"],
                json=dict(version=2, privacy_mode_enabled=True),
            )
            updates.append((changed.status_code, changed.json().get("code")))

    wire.before_chunk = enable_privacy
    response = await system.http.post(
        "/api/v1/quiz/generate",
        headers=account["headers"],
        json=dict(page_url="https://example.com/source", page_text=SOURCE),
    )
    assert updates == [(200, None)], updates
    assert response.status_code == 200, response.json()
    qid = response.json()["data"]["quiz_id"]
    async with system.db() as db:
        assert await db.get(QuizRecord, UUID(qid)) is None
    assert 0 < await system.cache.ttl(f"ephemeral_quiz:{qid}") <= 1800
    await system.cache.delete(f"ephemeral_quiz:{qid}")
    expired = await system.http.post(
        f"/api/v1/quiz/{qid}/submit",
        headers=account["headers"],
        json={"answers": {"1": 0, "2": 1, "3": 2}},
    )
    assert expired.status_code == 404 and expired.json()["code"] == "QUIZ_NOT_FOUND"


@pytest.mark.asyncio
async def test_real_redis_stream_concurrency_and_conversation_busy_guards(
    system, wire
) -> None:
    account = await system.account()
    await store_key(system, account, "openai")
    ready, release = asyncio.Event(), asyncio.Event()
    arrivals = 0

    async def pause(index: int) -> None:
        nonlocal arrivals
        if index == 0:
            arrivals += 1
            if arrivals == 2:
                ready.set()
            await release.wait()

    wire.before_chunk = pause
    payload = dict(
        task="explain",
        page_url="https://example.com/source",
        page_content=SOURCE,
        provider="openai",
        model="test-model",
        reading_session_id=str(uuid4()),
    )
    tasks = [
        asyncio.create_task(
            system.http.post(
                "/api/v1/ai/stream", headers=account["headers"], json=payload
            )
        )
        for _ in range(2)
    ]
    try:
        await asyncio.wait_for(ready.wait(), timeout=10)
        third = await system.http.post(
            "/api/v1/ai/stream", headers=account["headers"], json=payload
        )
        assert (
            third.status_code == 429
            and third.json()["code"] == "STREAM_CONCURRENCY_EXCEEDED"
        )
        async with system.db() as db:
            cid = await db.scalar(
                select(Conversation.id).where(
                    Conversation.user_id == UUID(account["id"])
                )
            )
        busy = await system.http.post(
            "/api/v1/ai/stream",
            headers=account["headers"],
            json={**payload, "conversation_id": str(cid)},
        )
        assert busy.status_code == 409 and busy.json()["code"] == "CONVERSATION_BUSY"
    finally:
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert all(sse_events(response)[-1][0] == "done" for response in responses)
    assert await system.cache.zcard(f"active_streams:{account['id']}") == 0
