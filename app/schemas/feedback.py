"""Voluntary diagnostic feedback shared with administrators."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import PostgresText, RequestModel


class AiFeedbackCreateRequest(RequestModel):
    """One rating on an owned assistant message."""

    message_id: UUID
    rating: Literal["helpful", "unhelpful"]
    report_reason: Literal["inaccurate", "hallucination", "harmful", "other"] | None = (
        None
    )
    comment: PostgresText | None = Field(None, max_length=4000)
