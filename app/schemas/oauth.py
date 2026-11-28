"""Validate external identity payloads before account lookup or database writes."""

from pydantic import BaseModel, Field, StrictBool, field_validator

from app.schemas.auth import UserRegisterRequest
from app.schemas.common import PostgresText


class OAuthEmail(BaseModel):
    """Require a real, bounded email string from the identity provider."""

    email: PostgresText = Field(strict=True, max_length=255)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        """Apply the same normalization and syntax boundary as registration."""
        return UserRegisterRequest.valid_email(value)


class GoogleIdentity(OAuthEmail):
    """Claims returned by Google's tokeninfo endpoint, not client-supplied claims."""

    sub: PostgresText = Field(strict=True, min_length=1, max_length=255)
    aud: str = Field(strict=True, min_length=1)
    iss: str = Field(strict=True, min_length=1)
    exp: int = Field(strict=True, gt=0)
    email_verified: StrictBool
    name: PostgresText | None = Field(None, strict=True)
    picture: PostgresText | None = Field(None, strict=True)

    @field_validator("exp", mode="before")
    @classmethod
    def tokeninfo_timestamp(cls, value: object) -> object:
        """Google tokeninfo may encode its integer timestamp as a decimal string."""
        if (
            isinstance(value, str)
            and value.isascii()
            and value.isdecimal()
            and len(value) <= 15
        ):
            return int(value)
        return value

    @field_validator("email_verified", mode="before")
    @classmethod
    def tokeninfo_boolean(cls, value: object) -> object:
        """Accept Google's explicit string booleans without truthiness coercion."""
        if value == "true":
            return True
        if value == "false":
            return False
        return value


class GitHubToken(BaseModel):
    """Successful code exchange must provide a non-empty bearer token."""

    access_token: str = Field(strict=True, min_length=1, max_length=8192)


class GitHubIdentity(BaseModel):
    """Stable GitHub user identity and optional display metadata."""

    id: int = Field(strict=True, gt=0)
    name: PostgresText | None = Field(None, strict=True)
    avatar_url: PostgresText | None = Field(None, strict=True)


class GitHubEmail(OAuthEmail):
    """Explicit verified/primary flags from the authenticated emails endpoint."""

    primary: StrictBool
    verified: StrictBool
