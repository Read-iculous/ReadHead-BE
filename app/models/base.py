"""Shared SQLAlchemy 2.0 column mixins."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base as Base


class Identity:
    """UUID identity generated on both Python and PostgreSQL sides."""

    id: Mapped[UUID] = mapped_column(
        primary_key=True, default=uuid4, server_default=text("gen_random_uuid()")
    )


class Created:
    """Creation timestamp in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Updated:
    """Last change timestamp, assigned explicitly by synchronized services."""

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
