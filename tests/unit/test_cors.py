"""Exercise the real application middleware stack without external services."""

from copy import copy
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from app.core import middleware
from app.core.exceptions import AppException
from app.main import app

EXTENSION_ORIGIN = "chrome-extension://" + "a" * 32


@pytest.fixture
def application(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """Keep production middleware configuration; isolate its runtime stack and I/O."""
    application = copy(app)
    application.middleware_stack = None
    pipeline = MagicMock()
    pipeline.__aenter__ = AsyncMock(return_value=pipeline)
    pipeline.__aexit__ = AsyncMock(return_value=None)
    pipeline.execute = AsyncMock(return_value=[])
    monkeypatch.setattr(
        middleware.redis.client, "pipeline", MagicMock(return_value=pipeline)
    )
    return application


@pytest.fixture
def limited(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Force the early-return branch without requiring Redis in unit tests."""
    limiter = AsyncMock(
        side_effect=AppException(
            429,
            "RATE_LIMIT_EXCEEDED",
            "Request rate limit exceeded",
            headers={"Retry-After": "30"},
        )
    )
    monkeypatch.setattr(middleware, "enforce_rate", limiter)
    return limiter


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [EXTENSION_ORIGIN, "http://localhost:3000"])
async def test_rate_limit_response_exposes_cors_headers(
    application: FastAPI,
    limited: AsyncMock,
    origin: str,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login", json={}, headers={"Origin": origin}
        )
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMIT_EXCEEDED"
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    exposed = {
        value.strip().lower()
        for value in response.headers["access-control-expose-headers"].split(",")
    }
    assert {"retry-after", "x-request-id"} <= exposed
    assert response.headers["retry-after"] == "30"
    assert response.headers["x-request-id"]
    assert "origin" in response.headers["vary"].lower()
    limited.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "https://untrusted.example",
        "chrome-extension://" + "q" * 32,
        EXTENSION_ORIGIN + ".untrusted.example",
    ],
)
async def test_rate_limit_response_does_not_allow_untrusted_origins(
    application: FastAPI,
    limited: AsyncMock,
    origin: str,
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/auth/login", json={}, headers={"Origin": origin}
        )
    assert response.status_code == 429
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_preflight_bypasses_rate_limit(
    application: FastAPI, limited: AsyncMock
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": EXTENSION_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == EXTENSION_ORIGIN
    assert "POST" in response.headers["access-control-allow-methods"]
    limited.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "status"),
    [("GET", "/api/v1/users/me", 401), ("POST", "/api/v1/auth/login", 422)],
)
async def test_handled_auth_and_validation_errors_keep_cors(
    application: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    status: int,
) -> None:
    monkeypatch.setattr(middleware, "enforce_rate", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.request(
            method,
            path,
            headers={"Origin": EXTENSION_ORIGIN},
            **({"json": {}} if method == "POST" else {}),
        )
    assert response.status_code == status
    assert response.headers["access-control-allow-origin"] == EXTENSION_ORIGIN


@pytest.mark.asyncio
async def test_non_browser_rate_limit_response_stays_readable(
    application: FastAPI, limited: AsyncMock
) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_swagger_validation_error_schema_matches_actual_response(
    application: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Swagger must describe the custom envelope, not FastAPI's default detail list."""
    monkeypatch.setattr(middleware, "enforce_rate", AsyncMock())
    schema = application.openapi()
    reference = schema["paths"]["/api/v1/auth/login"]["post"]["responses"]["422"][
        "content"
    ]["application/json"]["schema"]["$ref"]
    error_schema = schema["components"]["schemas"][reference.rsplit("/", 1)[1]]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422
    assert error_schema["properties"]["detail"]["type"] == "string"
    assert {"detail", "code"} <= set(error_schema["required"])
    assert isinstance(response.json()["detail"], str)
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin", [EXTENSION_ORIGIN, "http://localhost:3000", "https://untrusted.example"]
)
@pytest.mark.parametrize("failure", ["endpoint", "limiter", "token_decoder"])
async def test_unexpected_500_preserves_correlation_and_cors_policy(
    application: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    origin: str,
    failure: str,
) -> None:
    """Exercise Starlette's actual ServerErrorMiddleware response, not a mock 500."""
    from app.services import auth_service

    monkeypatch.setattr(middleware, "enforce_rate", AsyncMock())
    if failure == "endpoint":
        monkeypatch.setattr(
            auth_service,
            "login",
            AsyncMock(side_effect=RuntimeError("synthetic endpoint failure")),
        )
    elif failure == "limiter":
        monkeypatch.setattr(
            middleware,
            "enforce_rate",
            AsyncMock(side_effect=RuntimeError("synthetic limiter failure")),
        )
    else:
        monkeypatch.setattr(
            middleware,
            "decode_token",
            MagicMock(side_effect=RuntimeError("synthetic decoder failure")),
        )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/auth/login",
            headers={"Origin": origin, "Authorization": "Bearer synthetic-test-token"},
            json={"email": "reader@example.com", "password": "synthetic-password"},
        )
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Internal server error",
        "code": "INTERNAL_SERVER_ERROR",
        "field": None,
    }
    assert response.headers["x-request-id"]
    assert len(response.headers.get_list("x-request-id")) == 1
    if origin == "https://untrusted.example":
        assert "access-control-allow-origin" not in response.headers
    else:
        assert response.headers["access-control-allow-origin"] == origin
        assert response.headers["access-control-allow-credentials"] == "true"
        assert (
            "x-request-id" in response.headers["access-control-expose-headers"].lower()
        )
