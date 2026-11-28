"""Request correlation, asynchronous limits and content-free telemetry."""

import contextvars
import time
from uuid import uuid4

from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import redis
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.limiter import enforce_rate
from app.core.logging import request_id_context, user_id_context
from app.core.security import decode_token

PUBLIC_AUTH_PATHS = frozenset(
    {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/oauth/google",
        "/api/v1/auth/oauth/github",
        "/api/v1/auth/refresh",
    }
)


class CorrelationMiddleware:
    """Correlate every HTTP response, including outer server-error responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Keep the request ID active while error handlers render their response."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex

        async def correlated(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ] + [(b"x-request-id", request_id.encode())]
            await send(message)

        token = request_id_context.set(request_id)
        try:
            await self.app(scope, receive, correlated)
        finally:
            request_id_context.reset(token)


class OperationalMiddleware:
    """Observe an entire response, including SSE, without reading request bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Apply bounded limits and emit only aggregate operational counters."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        request_id = request_id_context.get() or uuid4().hex
        started = time.monotonic()
        status = 500
        path = scope.get("path", "")
        user_token: contextvars.Token[str | None] | None = None

        async def dispatch() -> None:
            """Keep early rate-limit responses inside correlation and telemetry."""
            nonlocal user_token
            uid = None
            header = request.headers.get("authorization", "")
            if header.lower().startswith("bearer "):
                try:
                    uid = decode_token(header[7:], "access")["sub"]
                except AppException:
                    pass
            user_token = user_id_context.set(uid)
            if (
                scope["method"] != "OPTIONS"
                and path.startswith("/api/v1/")
                and not path.startswith("/api/v1/health")
            ):
                group = (
                    "auth"
                    if path.startswith("/api/v1/auth/")
                    else (
                        "ai"
                        if path.startswith(("/api/v1/ai/", "/api/v1/quiz/"))
                        else "api"
                    )
                )
                cfg = get_settings()
                limit = {
                    "auth": cfg.auth_requests_per_minute,
                    "ai": cfg.ai_requests_per_minute,
                    "api": cfg.api_requests_per_minute,
                }[group]
                identity = request.client.host if request.client else "unknown"
                if path.rstrip("/") not in PUBLIC_AUTH_PATHS and uid:
                    identity = uid
                try:
                    await enforce_rate(
                        identity,
                        group,
                        limit,
                    )
                except AppException as exc:
                    response = JSONResponse(
                        exc.payload(), status_code=exc.status, headers=exc.headers
                    )
                    await response(scope, receive, observed)
                    return
            await self.app(scope, receive, observed)

        async def observed(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        context_token = request_id_context.set(request_id)
        try:
            await dispatch()
        finally:
            request_id_context.reset(context_token)
            if user_token is not None:
                user_id_context.reset(user_token)
            if path.startswith("/api/v1/") and not path.startswith("/api/v1/health"):
                try:
                    key = f"metrics:{int(time.time()//60)}"
                    async with redis.client.pipeline(transaction=True) as pipe:
                        pipe.hincrby(key, "requests", 1)
                        pipe.hincrby(key, "errors", int(status >= 400))
                        pipe.hincrbyfloat(
                            key, "latency_ms", (time.monotonic() - started) * 1000
                        )
                        pipe.expire(key, 31 * 86400)
                        await pipe.execute()
                except RedisError:
                    pass
