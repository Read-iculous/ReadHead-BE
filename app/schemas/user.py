"""Preferences, accessibility and account lifecycle input."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator

from app.core.privacy.domain_filter import normalize_domain
from app.schemas.common import (
    PostgresText,
    Provider,
    RequestModel,
    validate_bcrypt_password,
)


class AccessibilityProfileSchema(RequestModel):
    """Supported page accessibility preferences."""

    dyslexia_font: bool = False
    font_size_delta: int = Field(0, ge=-8, le=24)
    line_spacing: float = Field(1.5, ge=1, le=3)
    bionic_reading: bool = False
    high_contrast: bool = False


class UserSettingUpdateRequest(RequestModel):
    """Partial settings mutation requiring the client's base version."""

    version: int = Field(ge=1)
    default_provider: Provider | None = None
    default_model: PostgresText | None = Field(None, min_length=1, max_length=100)
    target_language: str | None = Field(None, pattern=r"^[a-z]{2}$")
    explanation_level: Literal["simple", "standard", "expert"] | None = None
    accessibility_profile: AccessibilityProfileSchema | None = None
    proactive_assistance_enabled: bool | None = None
    proactive_sensitivity: Literal["low", "medium", "high"] | None = None
    data_protection_mode: bool | None = None
    privacy_mode_enabled: bool | None = None
    blacklisted_domains: list[PostgresText] | None = Field(None, max_length=100)

    @model_validator(mode="after")
    def reject_nulls(self) -> "UserSettingUpdateRequest":
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Settings fields cannot be null")
        return self

    @field_validator("blacklisted_domains")
    @classmethod
    def valid_domains(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and any(
            not v or len(v) > 255 or "/" in v or ":" in v for v in values
        ):
            raise ValueError("Use hostname patterns, not URLs")
        return [normalize_domain(v) for v in values] if values is not None else None


class AccountDeleteRequest(RequestModel):
    """Explicit, authenticated account deletion confirmation."""

    confirmation: Literal["DELETE_ACCOUNT"]
    password: SecretStr | None = Field(None, min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def password_bytes(cls, value: SecretStr | None) -> SecretStr | None:
        """Bound confirmation before bcrypt can truncate or reject oversized input."""
        return validate_bcrypt_password(value) if value is not None else None
