"""Vault inputs; public responses contain only masked key hints."""

from pydantic import Field, SecretStr, field_validator

from app.schemas.common import Provider, RequestModel, validate_postgres_text


class ApiKeyCreateRequest(RequestModel):
    """Validate and atomically replace a provider key."""

    provider: Provider
    api_key: SecretStr = Field(min_length=8, max_length=4096)
    set_active: bool = True

    @field_validator("api_key")
    @classmethod
    def valid_key_text(cls, value: SecretStr) -> SecretStr:
        """Reject unsupported credential text before transport or hint persistence."""
        validate_postgres_text(value.get_secret_value())
        return value
