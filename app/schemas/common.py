"""Shared request validation and safe public serialization."""

from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)

Provider = Literal["openai", "gemini", "claude"]


def validate_postgres_text(value: str) -> str:
    """Reject text that cannot be represented in PostgreSQL UTF-8 text/JSONB."""
    if "\x00" in value:
        raise ValueError("Text must not contain NUL characters")
    value.encode("utf-8")
    return value


PostgresText = Annotated[str, AfterValidator(validate_postgres_text)]


def normalize_email(value: str) -> str:
    """Check the stored/query value after Unicode case folding can expand it."""
    normalized = validate_postgres_text(value.strip().casefold())
    if len(normalized) > 255:
        raise ValueError("Normalized email must not exceed 255 characters")
    return normalized


def validate_bcrypt_password(value: SecretStr, minimum: int = 1) -> SecretStr:
    """Reject unsupported bcrypt input and enforce the UTF-8 byte boundary."""
    raw = value.get_secret_value()
    if "\x00" in raw:
        raise ValueError("Password must not contain NUL characters")
    if not minimum <= len(raw.encode("utf-8")) <= 72:
        raise ValueError(f"Password must contain {minimum} to 72 UTF-8 bytes")
    return value


class RequestModel(BaseModel):
    """Strict request boundary rejecting unknown fields."""

    model_config = ConfigDict(extra="forbid")


def public(row: Any, fields: tuple[str, ...] | list[str]) -> dict:
    """Serialize only explicit public fields from an ORM entity."""
    return {key: getattr(row, key) for key in fields}


class Page(RequestModel):
    """Bounded page parameters."""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


def utf8(value: str, maximum: int) -> str:
    """Enforce byte limits for multilingual content."""
    if len(value.encode("utf-8")) > maximum:
        raise ValueError(f"Text exceeds {maximum} UTF-8 bytes")
    return value


class PageSource(RequestModel):
    """Validated source URL; never fetched automatically by the backend."""

    page_url: PostgresText = Field(max_length=8192)

    @field_validator("page_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https", "file"} or (
            parsed.scheme != "file" and not parsed.hostname
        ):
            raise ValueError("Expected an HTTP(S) page or local PDF file URL")
        return value
