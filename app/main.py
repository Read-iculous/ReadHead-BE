"""FastAPI entry point, error envelopes, CORS and dependency lifecycle."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.errors import ServerErrorMiddleware
from starlette.types import ASGIApp

from app.core import redis
from app.core.config import get_settings
from app.core.database import engine
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.core.middleware import CorrelationMiddleware, OperationalMiddleware
from app.routers.router import api_router
from app.schemas.responses import ApiErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Close connection pools on shutdown without modifying schema at startup."""
    configure_logging()
    yield
    await redis.client.aclose()
    await engine.dispose()


cfg = get_settings()


class ReadHeadApplication(FastAPI):
    """Wrap FastAPI's complete error stack with CORS and request correlation."""

    def build_middleware_stack(self) -> ASGIApp:
        """Include ServerErrorMiddleware responses in the outer HTTP observers."""
        stack = super().build_middleware_stack()
        if not isinstance(stack, ServerErrorMiddleware):
            raise RuntimeError("Expected FastAPI's outer server-error middleware")
        # Keep one framework error handler outside operational code, while CORS
        # and correlation enclose all responses it generates.
        stack.app = OperationalMiddleware(stack.app)
        return CORSMiddleware(
            CorrelationMiddleware(stack),
            allow_origins=[
                o.strip()
                for o in cfg.cors_origins.split(",")
                if o.strip() and o.strip() != "chrome-extension://*"
            ],
            allow_origin_regex=(
                r"^chrome-extension://[a-p]{32}$"
                if "chrome-extension://*" in cfg.cors_origins
                else None
            ),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )


app = ReadHeadApplication(
    title="ReadHead API",
    version="0.1.0",
    description="BYOK intelligent reading assistant. OAuth and real AI require user/provider configuration.",
    lifespan=lifespan,
    responses={
        422: {
            "model": ApiErrorResponse,
            "description": "Request validation or reading-source validation failed",
        }
    },
)


@app.exception_handler(AppException)
async def domain_error(request: Request, exc: AppException) -> JSONResponse:
    """Render domain failures without leaking SDK or database payloads."""
    from fastapi.encoders import jsonable_encoder

    return JSONResponse(
        jsonable_encoder(exc.payload()), status_code=exc.status, headers=exc.headers
    )


@app.exception_handler(RequestValidationError)
async def validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return only field locations, never invalid credential/body values."""
    errors = exc.errors()
    malformed = any(e["type"] == "json_invalid" for e in errors)
    selected = errors[0] if errors else None
    status, code, detail = 422, "VALIDATION_ERROR", "Request validation failed"
    if malformed:
        status, code, detail = 400, "INVALID_JSON", "Malformed JSON body"
        # A byte offset is not a field name; the envelope requires null here.
        selected = None
    else:
        mutation_error = next(
            (
                e
                for e in errors
                if len(e["loc"]) >= 3
                and e["loc"][:2] == ("body", "mutations")
                and isinstance(e["loc"][2], int)
            ),
            None,
        )
        provider_error = next(
            (
                e
                for e in errors
                if e["type"] == "literal_error"
                and e["loc"][-1:] in [("provider",), ("default_provider",)]
                and isinstance(e.get("input"), str)
            ),
            None,
        )
        if request.url.path.rstrip("/") == "/api/v1/sync/push" and mutation_error:
            selected = mutation_error
            status, code, detail = 400, "INVALID_SYNC_MUTATION", "Invalid sync mutation"
        elif provider_error:
            selected = provider_error
            status, code, detail = (
                400,
                "UNSUPPORTED_PROVIDER",
                "Provider is not supported",
            )
    locations = selected["loc"][1:] if selected else ()
    field = ".".join(str(v) for v in locations) if locations else None
    return JSONResponse(
        dict(
            detail=detail,
            code=code,
            field=field,
        ),
        status_code=status,
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    """Keep framework errors in the common envelope."""
    # FastAPI wraps decoding failures in HTTPException rather than schema errors.
    malformed_json = exc.status_code == 400 and isinstance(
        exc.__cause__, (UnicodeDecodeError, json.JSONDecodeError)
    )
    return JSONResponse(
        dict(
            detail=(
                "Malformed JSON body"
                if malformed_json
                else "Request could not be handled"
            ),
            code=(
                "INVALID_JSON"
                if malformed_json
                else (
                    "NOT_FOUND"
                    if exc.status_code == 404
                    else "UNAUTHORIZED" if exc.status_code == 401 else "VALIDATION_ERROR"
                )
            ),
            field=None,
        ),
        status_code=exc.status_code,
        headers=exc.headers,
    )


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Suppress SQL parameter values and internal connection strings."""
    logging.getLogger(__name__).error("database_operation_failed")
    return JSONResponse(
        dict(detail="Database operation failed", code="DATABASE_ERROR", field=None),
        status_code=500,
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log only a safe operational event, not raw exception values."""
    logging.getLogger(__name__).error("unhandled_request_failure")
    return JSONResponse(
        dict(detail="Internal server error", code="INTERNAL_SERVER_ERROR", field=None),
        status_code=500,
    )


app.include_router(api_router)
