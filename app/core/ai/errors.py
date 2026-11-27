"""Normalize upstream failures without returning raw SDK errors or credentials."""

import asyncio

import httpx

from app.core.exceptions import AppException


def provider_error(exc: Exception) -> AppException:
    """Map vendor transport/status exceptions to the shared error registry."""
    if isinstance(exc, AppException):
        return exc
    status = getattr(exc, "status_code", None)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
    if (
        isinstance(exc, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException))
        or "timeout" in type(exc).__name__.lower()
    ):
        return AppException(
            504, "UPSTREAM_AI_TIMEOUT", "AI provider timed out; retry manually"
        )
    if status in {402, 429}:
        return AppException(
            502,
            "UPSTREAM_QUOTA_EXCEEDED",
            "Provider quota or rate limit exceeded; check your provider account",
        )
    if status in {401, 403}:
        return AppException(
            400, "KEY_VALIDATION_FAILED", "Provider rejected the configured API key"
        )
    return AppException(
        502,
        "UPSTREAM_AI_ERROR",
        "AI provider could not complete the request; retry manually",
    )
