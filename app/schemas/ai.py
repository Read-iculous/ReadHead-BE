"""AI request contracts with explicit multilingual byte limits."""

from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.common import PageSource, PostgresText, Provider, RequestModel, utf8


class EphemeralTurn(RequestModel):
    """Client-owned private conversation turn, never persisted."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class AiStreamRequest(PageSource):
    """One tab-isolated explain/summarize/translate/simplify/chat operation."""

    task: Literal["explain", "summarize", "translate", "simplify", "chat"]
    target_language: str | None = Field(None, pattern=r"^[a-z]{2}$")
    conversation_id: UUID | None = None
    reading_session_id: UUID | None = None
    tab_id: int | None = None
    page_title: PostgresText | None = Field(None, max_length=500)
    selected_text: PostgresText = ""
    page_content: PostgresText = ""
    content_type: Literal["html_article", "pdf_text"] = "html_article"
    user_prompt: PostgresText = ""
    provider: Provider | None = None
    model: PostgresText | None = Field(None, min_length=1, max_length=100)
    bypass_protection: bool = False
    ephemeral_history: list[EphemeralTurn] = Field(default_factory=list, max_length=10)

    @field_validator("selected_text")
    @classmethod
    def selected_limit(cls, value: str) -> str:
        return utf8(value, 10000)

    @field_validator("page_content")
    @classmethod
    def page_limit(cls, value: str) -> str:
        return utf8(value, 102400)

    @field_validator("user_prompt")
    @classmethod
    def prompt_limit(cls, value: str) -> str:
        return utf8(value, 2000)

    @model_validator(mode="after")
    def valid_context(self) -> "AiStreamRequest":
        import json

        utf8(
            json.dumps(
                [t.model_dump() for t in self.ephemeral_history], ensure_ascii=False
            ),
            16384,
        )
        if not (
            self.selected_text.strip()
            or self.page_content.strip()
            or self.user_prompt.strip()
        ):
            raise ValueError("Provide source text or a question")
        return self


class SensitiveCheckRequest(RequestModel):
    """Pre-flight text inspection."""

    text: str = Field(max_length=150000)


class ProactiveSuggestRequest(PageSource):
    """Evaluate a reading slowdown without executing suggested actions."""

    paragraph_text: str = Field(min_length=1, max_length=20000)
    dwell_time_seconds: int = Field(ge=0, le=86400)
    bypass_protection: bool = False


class BindRequest(PageSource):
    """Transfer a conversation binding to the active reading tab."""

    reading_session_id: UUID
