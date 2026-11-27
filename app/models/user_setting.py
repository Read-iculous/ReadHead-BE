"""Versioned user preferences, accessibility and privacy policy."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, Identity, Updated

ACCESSIBILITY = dict(
    dyslexia_font=False,
    font_size_delta=0,
    line_spacing=1.5,
    bionic_reading=False,
    high_contrast=False,
)


class UserSetting(Identity, Updated, Base):
    """One settings record per user."""

    __tablename__ = "user_settings"
    __table_args__ = (
        Index(
            "idx_user_settings_blacklisted_domains",
            "blacklisted_domains",
            postgresql_using="gin",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    default_provider: Mapped[str] = mapped_column(
        String(50), default="gemini", server_default="gemini"
    )
    default_model: Mapped[str] = mapped_column(
        String(100), default="gemini-1.5-flash", server_default="gemini-1.5-flash"
    )
    target_language: Mapped[str] = mapped_column(
        String(10), default="vi", server_default="vi"
    )
    explanation_level: Mapped[str] = mapped_column(
        String(20), default="standard", server_default="standard"
    )
    accessibility_profile: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: dict(ACCESSIBILITY),
        server_default=text(
            '\'{"dyslexia_font": false, "font_size_delta": 0, "line_spacing": 1.5, "bionic_reading": false, "high_contrast": false}\'::jsonb'
        ),
    )
    proactive_assistance_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    proactive_sensitivity: Mapped[str] = mapped_column(
        String(20), default="medium", server_default="medium"
    )
    data_protection_mode: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true")
    )
    privacy_mode_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    blacklisted_domains: Mapped[list] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
