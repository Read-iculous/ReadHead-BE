"""Regressions for BE-01 error envelopes, 404 codes and log identity."""

import hashlib
import json
import logging
from copy import copy
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from app.core import middleware
from app.core.logging import JsonFormatter
from app.main import app


@pytest.fixture
def application(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Keep production handlers; isolate rate limiting and telemetry I/O."""
    isolated = copy(app)
    isolated.middleware_stack = None
    pipeline = MagicMock()
    pipeline.__aenter__ = AsyncMock(return_value=pipeline)
    pipeline.__aexit__ = AsyncMock(return_value=None)
    pipeline.execute = AsyncMock(return_value=[])
    monkeypatch.setattr(
        middleware.redis.client, "pipeline", MagicMock(return_value=pipeline)
    )
    monkeypatch.setattr(middleware, "enforce_rate", AsyncMock())
    return isolated


@pytest.mark.asyncio
async def test_malformed_json_has_null_field(application: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            content="{bad",
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 400
    assert response.json() == {
        "detail": "Malformed JSON body",
        "code": "INVALID_JSON",
        "field": None,
    }


@pytest.mark.asyncio
async def test_missing_body_has_null_field(application: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert response.json()["field"] is None


@pytest.mark.asyncio
async def test_unknown_route_uses_not_found_code(application: FastAPI) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/khong-ton-tai")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_formatter_masks_user_id_and_pii() -> None:
    record = logging.LogRecord(
        "app.test", logging.INFO, "x.py", 1, "login user@example.com", (), None
    )
    record.user_id = "user-123"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["user_id"] == hashlib.sha256(b"user-123").hexdigest()[:16]
    assert payload["message"] == "login [REDACTED]"
    assert "user-123" not in json.dumps(payload)


def test_formatter_user_id_is_null_without_identity() -> None:
    record = logging.LogRecord("app.test", logging.INFO, "x.py", 1, "tick", (), None)
    payload = json.loads(JsonFormatter().format(record))
    assert payload["user_id"] is None
