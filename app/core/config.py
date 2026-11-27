"""Validated runtime configuration and encryption keyring."""

import base64
from functools import lru_cache

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load application configuration from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    debug: bool = False
    port: int = 8000
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret_key: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(15, ge=1)
    refresh_token_expire_days: int = Field(30, ge=1)
    encryption_master_key: SecretStr | None = None
    encryption_master_keys: dict[str, SecretStr] = Field(default_factory=dict)
    current_key_version: str = "v1"
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")
    cors_origins: str = "chrome-extension://*"
    auth_requests_per_minute: int = Field(20, ge=1)
    ai_requests_per_minute: int = Field(30, ge=1)
    api_requests_per_minute: int = Field(120, ge=1)

    @property
    def keyring(self) -> dict[str, bytes]:
        """Return decoded effective AES-256 keys."""
        values = self.encryption_master_keys or (
            {self.current_key_version: self.encryption_master_key}
            if self.encryption_master_key
            else {}
        )
        return {
            version: base64.b64decode(
                value.get_secret_value(), altchars=b"-_", validate=True
            )
            for version, value in values.items()
        }

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        """Fail startup on invalid, weak or reused secrets."""
        signing = self.jwt_secret_key.get_secret_value()
        if len(signing) < 32 or signing.startswith("change_this"):
            raise ValueError(
                "JWT_SECRET_KEY must be a generated secret of at least 32 characters"
            )
        if self.jwt_algorithm not in {"HS256", "HS384", "HS512"}:
            raise ValueError("Use an explicitly supported HMAC JWT algorithm")
        keys = self.keyring
        if self.current_key_version not in keys or any(
            len(k) != 32 for k in keys.values()
        ):
            raise ValueError(
                "Keyring must contain CURRENT_KEY_VERSION and 32-byte keys"
            )
        if len(set(keys.values())) != len(keys):
            raise ValueError("Keyring versions must use distinct key material")
        raw_values = self.encryption_master_keys or (
            {self.current_key_version: self.encryption_master_key}
            if self.encryption_master_key
            else {}
        )
        if any(signing == v.get_secret_value() for v in raw_values.values()):
            raise ValueError("JWT and encryption secrets must differ")
        if signing.encode() in keys.values():
            raise ValueError("JWT and encryption secrets must differ")
        if not self.database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return self


@lru_cache
def get_settings() -> Settings:
    """Build one validated settings instance per process."""
    return Settings()
