"""Administrative account moderation input."""

from typing import Literal

from app.schemas.common import RequestModel


class UserStatusUpdateRequest(RequestModel):
    """Change another account's moderation status."""

    status: Literal["active", "suspended", "banned"]
