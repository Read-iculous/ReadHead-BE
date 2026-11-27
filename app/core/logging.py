"""Allowlisted structured logging without request bodies or raw exceptions."""

import hashlib
import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone

from app.core.privacy.pii_detector import inspect

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_context: ContextVar[str | None] = ContextVar("user_id", default=None)


def mask_user_id(value: str | None) -> str | None:
    """Correlate a user without exposing its raw identifier in logs."""
    return hashlib.sha256(value.encode()).hexdigest()[:16] if value else None


class JsonFormatter(logging.Formatter):
    """Emit sanitized operational fields; suppress exception text and payloads."""

    def format(self, record: logging.LogRecord) -> str:
        message = inspect(record.getMessage())[1]
        return json.dumps(
            dict(
                timestamp=datetime.now(timezone.utc).isoformat(),
                level=record.levelname,
                service="readhead",
                message=message[:500],
                request_id=getattr(record, "request_id", request_id_context.get()),
                user_id=mask_user_id(
                    getattr(record, "user_id", None) or user_id_context.get()
                ),
            ),
            ensure_ascii=False,
        )


def configure_logging() -> None:
    """Install the JSON formatter and quiet sensitive upstream transport logs."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
    for name in ("httpx", "httpcore", "openai", "anthropic", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(logging.CRITICAL)
