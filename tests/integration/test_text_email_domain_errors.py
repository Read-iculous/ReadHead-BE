"""PostgreSQL text boundaries and documented validation error classifications."""

from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models.highlight import Highlight
from app.models.reading_history import ReadingHistory
from app.models.user import User
from tests.integration.provider_wire import ProviderWire
from tests.integration.test_ai_quiz_oauth_admin import SOURCE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload", "field"),
    [
        (
            "/api/v1/reading/highlights",
            {
                "page_url": "https://example.com/source",
                "highlighted_text": "PDF extracted\x00text",
            },
            "highlighted_text",
        ),
        (
            "/api/v1/reading/highlights",
            {
                "page_url": "https://example.com/source",
                "highlighted_text": "Valid text",
                "user_note": "note\x00text",
            },
            "user_note",
        ),
        (
            "/api/v1/reading/highlights",
            {
                "page_url": "https://example.com/a\x00b",
                "highlighted_text": "Valid text",
            },
            "page_url",
        ),
        (
            "/api/v1/reading/history",
            {"page_url": "https://example.com/source", "page_title": "PDF\x00title"},
            "page_title",
        ),
        (
            "/api/v1/reading/history",
            {
                "page_url": "https://example.com/source",
                "cached_summary": "summary\x00text",
            },
            "cached_summary",
        ),
        (
            "/api/v1/ai/stream",
            {
                "task": "explain",
                "page_url": "https://example.com/source",
                "user_prompt": "Explain\x00this",
            },
            "user_prompt",
        ),
        (
            "/api/v1/ai/stream",
            {
                "task": "explain",
                "page_url": "https://example.com/source",
                "selected_text": "Selected\x00text",
            },
            "selected_text",
        ),
        (
            "/api/v1/ai/stream",
            {
                "task": "explain",
                "page_url": "https://example.com/source",
                "page_content": SOURCE,
                "page_title": "PDF\x00title",
            },
            "page_title",
        ),
        (
            "/api/v1/ai/feedback",
            {
                "message_id": str(uuid4()),
                "rating": "helpful",
                "comment": "Comment\x00text",
            },
            "comment",
        ),
    ],
)
async def test_nul_db_text_is_rejected_before_service_writes(
    system: SimpleNamespace, wire: ProviderWire, path: str, payload: dict, field: str
) -> None:
    account = await system.account()
    response = await system.http.post(path, headers=account["headers"], json=payload)
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] == field
    assert not wire.calls
    async with system.db() as db:
        for model in [Highlight, ReadingHistory]:
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(model)
                    .where(model.user_id == UUID(account["id"]))
                )
                == 0
            )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "query", "field"),
    [
        ("/api/v1/reading/history", "search", "search"),
        ("/api/v1/reading/highlights", "page_url", "page_url"),
        ("/api/v1/conversations", "search", "search"),
    ],
)
async def test_nul_query_text_never_reaches_postgres(
    system: SimpleNamespace, path: str, query: str, field: str
) -> None:
    account = await system.account()
    response = await system.http.get(
        path, headers=account["headers"], params={query: "bad\x00filter"}
    )
    assert response.status_code == 422 and response.json()["field"] == field


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["register", "login"])
async def test_email_length_is_checked_after_casefold(
    system: SimpleNamespace, endpoint: str
) -> None:
    # Raw 137 characters, normalized 262 characters: exceeds users.email VARCHAR(255).
    email = "İ" * 125 + "@example.com"
    before = len(system.emails)
    response = await system.http.post(
        f"/api/v1/auth/{endpoint}",
        json={"email": email, "password": "Valid-test-password-123"},
    )
    assert response.status_code == 422 and response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] == "email"
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(User)
                .where(User.email == email.casefold())
            )
            == 0
        )
    assert len(system.emails) == before


@pytest.mark.asyncio
async def test_normalized_email_at_column_boundary_remains_usable(
    system: SimpleNamespace,
) -> None:
    # 121 casefold-expanding letters + 13 ASCII chars == 255 after normalization.
    email = "İ" * 121 + "x@example.com"
    normalized = email.casefold()
    assert len(normalized) == 255
    system.emails.append(normalized)
    created = await system.http.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Valid-test-password-123"},
    )
    assert created.status_code == 201
    login = await system.http.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Valid-test-password-123"},
    )
    assert login.status_code == 200
    async with system.db() as db:
        assert (
            await db.scalar(
                select(User.email).where(User.id == UUID(created.json()["data"]["id"]))
            )
            == normalized
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation_change",
    [
        {"entity_type": "unknown"},
        {"action": "unknown"},
        {"base_version": 0},
        {"payload": []},
    ],
)
async def test_invalid_mutation_schema_uses_documented_domain_error(
    system: SimpleNamespace, mutation_change: dict
) -> None:
    account = await system.account()
    mutation = dict(
        entity_type="highlight",
        action="update",
        entity_id=str(uuid4()),
        base_version=1,
        payload={"user_note": "Valid note"},
    )
    response = await system.http.post(
        "/api/v1/sync/push",
        headers=account["headers"],
        json={"mutations": [{**mutation, **mutation_change}]},
    )
    assert (
        response.status_code == 400
        and response.json()["code"] == "INVALID_SYNC_MUTATION"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "payload", "field"),
    [
        (
            "POST",
            "/api/v1/api-keys",
            {"provider": "unknown", "api_key": "synthetic-test-credential"},
            "provider",
        ),
        (
            "POST",
            "/api/v1/ai/stream",
            {
                "provider": "unknown",
                "task": "explain",
                "page_url": "https://example.com/source",
                "page_content": SOURCE,
            },
            "provider",
        ),
        (
            "PATCH",
            "/api/v1/users/me/settings",
            {"version": 1, "default_provider": "unknown"},
            "default_provider",
        ),
        ("POST", "/api/v1/api-keys/unknown/validate", None, "provider"),
        ("DELETE", "/api/v1/api-keys/unknown", None, "provider"),
    ],
)
async def test_unsupported_provider_uses_documented_domain_error(
    system: SimpleNamespace,
    wire: ProviderWire,
    method: str,
    path: str,
    payload: dict | None,
    field: str,
) -> None:
    account = await system.account()
    kwargs = {"json": payload} if payload is not None else {}
    response = await system.http.request(
        method, path, headers=account["headers"], **kwargs
    )
    assert (
        response.status_code == 400
        and response.json()["code"] == "UNSUPPORTED_PROVIDER"
    )
    assert response.json()["field"] == field
    assert not wire.calls


@pytest.mark.asyncio
async def test_nul_sync_payload_rolls_back_entire_batch(
    system: SimpleNamespace,
) -> None:
    account = await system.account()
    saved = await system.http.post(
        "/api/v1/reading/highlights",
        headers=account["headers"],
        json=dict(
            page_url="https://example.com/source",
            highlighted_text="Valid UTF-8: Tiếng Việt 日本語 😀",
        ),
    )
    assert saved.status_code == 201
    hid = saved.json()["data"]["id"]
    mutation = dict(
        entity_type="highlight",
        entity_id=hid,
        action="update",
        base_version=1,
        payload={"color": "blue"},
    )
    response = await system.http.post(
        "/api/v1/sync/push",
        headers=account["headers"],
        json={
            "mutations": [
                mutation,
                {
                    **mutation,
                    "base_version": 2,
                    "payload": {"user_note": "invalid\x00note"},
                },
            ]
        },
    )
    assert (
        response.status_code == 400
        and response.json()["code"] == "INVALID_SYNC_MUTATION"
    )
    async with system.db() as db:
        row = await db.get(Highlight, UUID(hid))
        assert row.version == 1 and row.color == "yellow" and row.user_note is None


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [None, 123, ["openai"]])
async def test_provider_type_errors_remain_validation_errors(system, provider) -> None:
    account = await system.account()
    response = await system.http.post(
        "/api/v1/api-keys",
        headers=account["headers"],
        json={"provider": provider, "api_key": "synthetic-test-credential"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_domain_error_mapping_preserves_json_and_other_enum_errors(
    system,
) -> None:
    account = await system.account()
    invalid_task = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json={
            "task": "unknown",
            "page_url": "https://example.com",
            "page_content": SOURCE,
        },
    )
    assert invalid_task.status_code == 422
    assert invalid_task.json()["code"] == "VALIDATION_ERROR"
    malformed = await system.http.post(
        "/api/v1/sync/push",
        headers={**account["headers"], "Content-Type": "application/json"},
        content='{"mutations": [',
    )
    assert malformed.status_code == 400
    assert malformed.json()["code"] == "INVALID_JSON"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"email": "İ" * 125 + "@example.com"},
        {"name": "Bad\x00name"},
        {"sub": "Bad\x00subject"},
    ],
)
async def test_invalid_external_identity_text_is_an_auth_error(
    system, wire, change
) -> None:
    email = change.get("email", wire.google["email"]).casefold()
    system.emails.append(email)
    wire.google.update(change)
    response = await system.http.post(
        "/api/v1/auth/oauth/google", json={"id_token": "synthetic-invalid-text"}
    )
    assert response.status_code == 401 and response.json()["code"] == "TOKEN_INVALID"
    async with system.db() as db:
        assert await db.scalar(select(User.id).where(User.email == email)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{"default_model": "bad\x00model"}, {"blacklisted_domains": ["bad\x00.example"]}],
)
async def test_invalid_settings_text_in_sync_is_domain_error(system, payload) -> None:
    from app.models.user_setting import UserSetting

    account = await system.account()
    async with system.db() as db:
        setting = await db.scalar(
            select(UserSetting).where(UserSetting.user_id == UUID(account["id"]))
        )
        sid = setting.id
    response = await system.http.post(
        "/api/v1/sync/push",
        headers=account["headers"],
        json={
            "mutations": [
                dict(
                    entity_type="settings",
                    action="update",
                    entity_id=str(sid),
                    base_version=1,
                    payload=payload,
                )
            ]
        },
    )
    assert (
        response.status_code == 400
        and response.json()["code"] == "INVALID_SYNC_MUTATION"
    )
    async with system.db() as db:
        row = await db.get(UserSetting, sid)
        assert row.version == 1 and row.blacklisted_domains == []


@pytest.mark.asyncio
async def test_nul_upstream_stream_is_rejected_before_assistant_write(
    system, wire
) -> None:
    from app.models.conversation import Conversation, Message
    from tests.integration.test_ai_quiz_oauth_admin import sse_events, store_key

    account = await system.account()
    await store_key(system, account, "openai")
    wire.output = "Bad\x00answer"
    response = await system.http.post(
        "/api/v1/ai/stream",
        headers=account["headers"],
        json=dict(
            task="explain",
            page_url="https://example.com",
            page_content=SOURCE,
            provider="openai",
            model="test-model",
            reading_session_id=str(uuid4()),
        ),
    )
    events = sse_events(response)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "UPSTREAM_AI_ERROR"
    assert not any(name == "done" for name, _ in events)
    async with system.db() as db:
        assert (
            await db.scalar(
                select(func.count())
                .select_from(Message)
                .join(Conversation)
                .where(
                    Conversation.user_id == UUID(account["id"]),
                    Message.sender_role == "assistant",
                )
            )
            == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["question_text", "options", "explanation"])
async def test_nul_generated_quiz_text_is_upstream_error(system, wire, field) -> None:
    import copy
    import json

    from app.models.quiz import QuizRecord
    from tests.integration.test_ai_quiz_oauth_admin import QUIZ, store_key

    account = await system.account()
    await store_key(system, account, "openai")
    changed = await system.http.patch(
        "/api/v1/users/me/settings",
        headers=account["headers"],
        json=dict(version=1, default_provider="openai", default_model="test-model"),
    )
    assert changed.status_code == 200
    quiz = copy.deepcopy(QUIZ)
    quiz["questions"][0][field] = (
        ["Bad\x00option", "B", "C", "D"] if field == "options" else "Bad\x00text"
    )
    wire.output = json.dumps(quiz)
    response = await system.http.post(
        "/api/v1/quiz/generate",
        headers=account["headers"],
        json=dict(page_url="https://example.com", page_text=SOURCE),
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
