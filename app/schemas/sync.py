"""Bounded multi-device pull/push contracts."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import RequestModel


class SyncPullRequest(RequestModel):
    """One server-issued opaque position/checkpoint cursor."""

    cursor: str | None = Field(None, max_length=2048)
    limit: int = Field(100, ge=1, le=100)


class SyncMutation(RequestModel):
    """A versioned mutation; only explicitly mutable fields are accepted."""

    entity_type: Literal["conversation", "highlight", "settings"]
    action: Literal["update", "delete"]
    entity_id: UUID
    base_version: int = Field(ge=1)
    payload: dict = Field(default_factory=dict)


class SyncPushRequest(RequestModel):
    """Atomic batch of local non-AI mutations."""

    mutations: list[SyncMutation] = Field(min_length=1, max_length=100)
