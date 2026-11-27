"""Regression coverage for optional filters, cursor types, passwords and tab binding."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr, ValidationError

from app.core.auth import Principal, get_current_user
from app.core.exceptions import AppException
from app.main import domain_error, validation_error
from app.routers import reading, sync
from app.schemas.ai import AiStreamRequest
from app.schemas.auth import UserLoginRequest, UserRegisterRequest
from app.services import ai_service, auth_service, reading_service, sync_service


@pytest.fixture
def principal() -> Principal:
    """Create a detached fake identity without a database session."""
    return Principal(uuid4(), uuid4(), "user")


@pytest.fixture
def application(principal: Principal) -> FastAPI:
    """Mount real routers/error handlers without infrastructure middleware."""
    from fastapi.exceptions import RequestValidationError

    app = FastAPI()
    app.include_router(reading.router, prefix="/api/v1")
    app.include_router(sync.router, prefix="/api/v1")
    app.add_exception_handler(AppException, domain_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.dependency_overrides[get_current_user] = lambda: principal
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "method", "filter_name"),
    [
        ("/api/v1/reading/history", "list_history", "search"),
        ("/api/v1/reading/highlights", "list_highlights", "page_url"),
    ],
)
async def test_list_without_filter_returns_200(
    application: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    method: str,
    filter_name: str,
) -> None:
    result = {
        "data": {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 0}
    }
    service = AsyncMock(return_value=result)
    monkeypatch.setattr(reading_service, method, service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(path)
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []
    assert service.await_args.args[-1] is None
    parameter = next(
        p
        for p in application.openapi()["paths"][path]["get"]["parameters"]
        if p["name"] == filter_name
    )
    assert parameter["required"] is False


def cursor_payload(**updates: object) -> dict:
    """Return a current valid cursor that tests can corrupt field by field."""
    now = datetime.now(timezone.utc).isoformat()
    return {"v": 1, "kind": "checkpoint", "t": now, "anchor": now, **updates}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["t", "anchor"])
@pytest.mark.parametrize("value", [1, 1.5, None, True, [], {}])
async def test_invalid_cursor_timestamp_type_returns_400(
    application: FastAPI,
    name: str,
    value: object,
) -> None:
    payload = cursor_payload(**{name: value})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/sync/pull", json={"cursor": sync_service.encode_cursor(payload)}
        )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_SYNC_CURSOR"


@pytest.mark.parametrize("name", ["id", "entity_type"])
@pytest.mark.parametrize("value", [1, None, True, [], {}])
def test_invalid_position_cursor_field_type_is_a_domain_error(
    name: str, value: object
) -> None:
    payload = cursor_payload(
        kind="position", entity_type="conversation", id=str(uuid4())
    )
    payload[name] = value
    with pytest.raises(AppException) as failure:
        sync_service.decode_cursor(sync_service.encode_cursor(payload))
    assert failure.value.status == 400
    assert failure.value.code == "INVALID_SYNC_CURSOR"


@pytest.mark.parametrize("version", [True, 1.0])
def test_cursor_version_requires_an_integer(version: object) -> None:
    with pytest.raises(AppException) as failure:
        sync_service.decode_cursor(
            sync_service.encode_cursor(cursor_payload(v=version))
        )
    assert failure.value.code == "INVALID_SYNC_CURSOR"


def test_valid_position_cursor_preserves_uuid() -> None:
    identity = uuid4()
    decoded = sync_service.decode_cursor(
        sync_service.encode_cursor(
            cursor_payload(kind="position", entity_type="highlight", id=str(identity))
        )
    )
    assert decoded["id"] == identity


def test_login_accepts_exactly_72_utf8_bytes() -> None:
    password = "😀" * 18
    registered = UserRegisterRequest(
        email="reader@example.com", password=SecretStr(password)
    )
    login = UserLoginRequest(email=registered.email, password=SecretStr(password))
    assert len(login.password.get_secret_value().encode("utf-8")) == 72


@pytest.mark.parametrize("password", ["😀" * 18 + "x", "é" * 36 + "x", "a" * 73])
def test_login_rejects_password_exceeding_72_utf8_bytes(password: str) -> None:
    with pytest.raises(ValidationError):
        UserLoginRequest(email="reader@example.com", password=SecretStr(password))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "binding",
    ["both_missing", "stored_missing", "request_missing", "mismatched", "matched"],
)
async def test_existing_conversation_requires_matching_non_null_binding(
    principal: Principal,
    monkeypatch: pytest.MonkeyPatch,
    binding: str,
) -> None:
    stored = uuid4() if binding not in {"both_missing", "stored_missing"} else None
    requested = (
        None
        if binding in {"both_missing", "request_missing"}
        else (stored if binding == "matched" else uuid4())
    )
    conversation = SimpleNamespace(
        reading_session_id=stored, page_url="https://example.com/article", version=1
    )
    settings = SimpleNamespace(
        privacy_mode_enabled=False,
        default_provider="openai",
        default_model="test-model",
        target_language="vi",
        explanation_level="standard",
    )
    db = MagicMock()
    db.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

    @asynccontextmanager
    async def fake_transaction():
        yield db

    monkeypatch.setattr(ai_service, "transaction", fake_transaction)
    monkeypatch.setattr(ai_service, "settings_for", AsyncMock(return_value=settings))
    monkeypatch.setattr(ai_service, "owned", AsyncMock(return_value=conversation))
    monkeypatch.setattr(ai_service, "active_key", AsyncMock(return_value="mock-key"))
    monkeypatch.setattr(ai_service, "enforce", MagicMock())
    monkeypatch.setattr(
        ai_service, "sync_stamp", AsyncMock(return_value=datetime.now(timezone.utc))
    )
    monkeypatch.setattr(auth_service, "checked_session", AsyncMock())
    lease = SimpleNamespace(acquire=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(ai_service.redis, "StreamLease", MagicMock(return_value=lease))
    monkeypatch.setattr(ai_service.ProviderFactory, "create", MagicMock())
    request = AiStreamRequest(
        task="chat",
        page_url="https://example.com/article",
        conversation_id=uuid4(),
        reading_session_id=requested,
        user_prompt="Explain this paragraph",
    )
    if binding == "matched":
        prepared = await ai_service.prepare(principal, request)
        assert prepared.cid == request.conversation_id
        lease.acquire.assert_awaited_once()
        db.add.assert_called_once()
    else:
        with pytest.raises(AppException) as failure:
            await ai_service.prepare(principal, request)
        assert failure.value.code == "TAB_CONTEXT_MISMATCH"
        assert failure.value.status == 400
        lease.acquire.assert_not_awaited()
        db.add.assert_not_called()
