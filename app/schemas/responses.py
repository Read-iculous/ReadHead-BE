"""Explicit public response schemas; secret ORM fields cannot escape these boundaries."""

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiErrorResponse(BaseModel):
    """Document the shared error envelope and optional domain-specific metadata."""

    model_config = ConfigDict(extra="allow")

    detail: str
    code: str
    field: str | None = None


class PublicModel(BaseModel):
    """Serialize only declared public attributes."""

    model_config = ConfigDict(from_attributes=True)


class Envelope(BaseModel, Generic[T]):
    """Standard single-resource success envelope."""

    data: T
    message: str | None = None


class PageData(BaseModel, Generic[T]):
    """Bounded list metadata nested inside data."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class TokenResponse(PublicModel):
    """Public JWT pair; hashes/session metadata remain internal."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"]
    expires_in: int


class UserResponse(PublicModel):
    """Account profile without hashes or server-only sync clock."""

    id: UUID
    email: str
    full_name: str | None
    avatar_url: str | None = None
    role: str
    status: str
    is_verified: bool
    created_at: datetime
    linked_accounts: list[str] = Field(default_factory=list)


class ApiKeyResponse(PublicModel):
    """Masked vault metadata only."""

    id: UUID
    provider: str
    key_hint: str
    is_active: bool
    last_validated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserSettingResponse(PublicModel):
    """Versioned user configuration."""

    id: UUID
    default_provider: str
    default_model: str
    target_language: str
    explanation_level: str
    accessibility_profile: dict
    proactive_assistance_enabled: bool
    proactive_sensitivity: str
    data_protection_mode: bool
    privacy_mode_enabled: bool
    blacklisted_domains: list[str]
    version: int
    updated_at: datetime


class ConversationResponse(PublicModel):
    """Owned conversation metadata, never loaded ORM relationships."""

    id: UUID
    title: str
    page_url: str | None
    page_title: str | None
    reading_session_id: UUID | None
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class MessageResponse(PublicModel):
    """Immutable turn and conservative attribution metadata."""

    id: UUID
    sender_role: str
    content: str
    selected_context: str | None
    provider_used: str | None
    model_used: str | None
    is_grounded: bool
    uncertainty_flag: bool
    grounding_notes: str | None
    created_at: datetime


class HighlightResponse(PublicModel):
    """Versioned explicit saved selection."""

    id: UUID
    page_url: str
    highlighted_text: str
    user_note: str | None
    color: str
    version: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime


class ReadingHistoryResponse(PublicModel):
    """Recorded reading visit outside Privacy Mode."""

    id: UUID
    page_url: str
    page_title: str | None
    cached_summary: str | None
    reading_time_seconds: int
    is_bookmarked: bool
    visited_at: datetime
