"""Reading history and highlight payloads."""

from typing import Literal

from pydantic import Field

from app.schemas.common import PageSource, PostgresText


class ReadingHistoryCreate(PageSource):
    """Record one reading visit outside Privacy Mode."""

    page_title: PostgresText | None = Field(None, max_length=500)
    reading_time_seconds: int = Field(0, ge=0, le=86400)
    cached_summary: PostgresText | None = Field(None, max_length=100000)


class HighlightCreate(PageSource):
    """An explicit user save that is permitted in Privacy Mode."""

    highlighted_text: PostgresText = Field(min_length=1, max_length=10000)
    user_note: PostgresText | None = Field(None, max_length=10000)
    color: Literal["yellow", "green", "blue", "pink"] = "yellow"
