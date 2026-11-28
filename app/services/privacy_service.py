"""Common outbound privacy enforcement for every AI-producing operation."""

import logging

from app.core.auth import Principal
from app.core.exceptions import AppException
from app.core.privacy.domain_filter import blocked
from app.core.privacy.pii_detector import inspect
from app.models.user_setting import UserSetting


def enforce(
    settings: UserSetting,
    url: str,
    text: str,
    bypass: bool = False,
    *,
    audit: bool = True,
) -> None:
    """Inspect all outbound context before a provider sees any user material."""
    if blocked(url, settings.blacklisted_domains):
        raise AppException(
            400,
            "DOMAIN_BLOCKED_BY_PRIVACY",
            "This domain is blocked by privacy settings",
        )
    types, preview = inspect(text)
    if settings.data_protection_mode and types and not bypass:
        raise AppException(
            400,
            "SENSITIVE_DATA_DETECTED",
            "Sensitive content requires explicit confirmation",
            detected_types=types,
            redacted_preview=preview[:300],
        )
    if types and bypass and audit:
        logging.getLogger(__name__).info("sensitive_content_override_confirmed")


async def check_sensitive(principal: Principal, text: str) -> dict:
    """Return a redacted pre-flight result without storing source text."""
    from app.core.database import transaction
    from app.services.common import settings_for

    async with transaction() as db:
        settings = await settings_for(db, principal.user_id)
        types, preview = inspect(text)
        return {
            "data": dict(
                is_sensitive=bool(types),
                detected_types=types,
                redacted_preview=preview[:500],
                blocked_by_policy=bool(types) and settings.data_protection_mode,
            )
        }
