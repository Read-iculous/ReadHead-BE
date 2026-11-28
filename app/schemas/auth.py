"""Account registration and token requests."""

import re

from pydantic import Field, SecretStr, field_validator

from app.schemas.common import (
    PostgresText,
    RequestModel,
    normalize_email,
    validate_bcrypt_password,
)


class UserRegisterRequest(RequestModel):
    """Create an email/password account."""

    email: PostgresText = Field(max_length=255)
    password: SecretStr
    full_name: PostgresText | None = Field(None, max_length=150)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = normalize_email(value)
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Invalid email address")
        return value

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: SecretStr) -> SecretStr:
        return validate_bcrypt_password(value, minimum=8)


class UserLoginRequest(RequestModel):
    """Authenticate an existing email account."""

    email: PostgresText = Field(max_length=255)
    password: SecretStr = Field(min_length=1, max_length=72)

    @field_validator("email")
    @classmethod
    def normalized_email(cls, value: str) -> str:
        """Enforce the same normalized column boundary before querying users."""
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def valid_password(cls, value: SecretStr) -> SecretStr:
        """Reject UTF-8 overflow before bcrypt can truncate a different password."""
        return validate_bcrypt_password(value)


class TokenRefreshRequest(RequestModel):
    """Supply a signed refresh token without exposing it in repr."""

    refresh_token: SecretStr = Field(min_length=1, max_length=4096)


class GoogleAuthRequest(RequestModel):
    """Google Identity token."""

    id_token: SecretStr = Field(min_length=1, max_length=8192)


class GitHubAuthRequest(RequestModel):
    """GitHub authorization code."""

    code: SecretStr = Field(min_length=1, max_length=1024)
