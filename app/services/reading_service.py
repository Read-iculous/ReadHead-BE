"""Reading logs and explicit saved highlights with privacy and sync semantics."""

from uuid import UUID

from sqlalchemy import delete, func, select, update

from app.core.auth import Principal
from app.core.database import transaction
from app.core.privacy.domain_filter import blocked
from app.models.conversation import Conversation
from app.models.highlight import Highlight
from app.models.reading_history import ReadingHistory
from app.schemas.common import public
from app.schemas.reading import HighlightCreate, ReadingHistoryCreate
from app.services.common import (
    HIGHLIGHT_FIELDS,
    HISTORY_FIELDS,
    lock_user,
    owned,
    paginate,
    settings_for,
    sync_stamp,
)


async def record_history(principal: Principal, data: ReadingHistoryCreate) -> dict:
    """Skip automatic logging for private or blacklisted reading contexts."""
    async with transaction() as db:
        await lock_user(db, principal.user_id)
        settings = await settings_for(db, principal.user_id)
        if settings.privacy_mode_enabled or blocked(
            data.page_url, settings.blacklisted_domains
        ):
            return {
                "data": None,
                "message": "History logging skipped by privacy policy",
            }
        row = ReadingHistory(user_id=principal.user_id, **data.model_dump())
        db.add(row)
        await db.flush()
        return {"data": public(row, HISTORY_FIELDS)}


async def list_history(
    principal: Principal, page: int, page_size: int, search: str | None
) -> dict:
    """Return only this account's paginated reading visits."""
    async with transaction() as db:
        q = select(ReadingHistory).where(ReadingHistory.user_id == principal.user_id)
        if search:
            q = q.where(ReadingHistory.page_title.icontains(search, autoescape=True))
        return await paginate(
            db,
            q.order_by(ReadingHistory.visited_at.desc(), ReadingHistory.id),
            HISTORY_FIELDS,
            page,
            page_size,
        )


async def clear_history(principal: Principal) -> None:
    """Clear visits and synchronize removal of conversation URL footprints."""
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        await db.execute(
            delete(ReadingHistory).where(ReadingHistory.user_id == principal.user_id)
        )
        await db.execute(
            update(Conversation)
            .where(Conversation.user_id == principal.user_id)
            .values(
                page_url=None,
                page_title=None,
                version=Conversation.version + 1,
                updated_at=stamp,
            )
        )


async def create_highlight(principal: Principal, data: HighlightCreate) -> dict:
    """Persist an explicit Save Highlight action even in Privacy Mode."""
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        row = Highlight(
            user_id=principal.user_id, updated_at=stamp, **data.model_dump()
        )
        db.add(row)
        await db.flush()
        return {"data": public(row, HIGHLIGHT_FIELDS)}


async def list_highlights(
    principal: Principal, page: int, page_size: int, page_url: str | None
) -> dict:
    """List live highlights with an optional exact page filter."""
    async with transaction() as db:
        q = select(Highlight).where(
            Highlight.user_id == principal.user_id, Highlight.is_deleted.is_(False)
        )
        if page_url:
            # Digest bounds index entries; exact equality protects against collisions.
            q = q.where(
                func.md5(Highlight.page_url) == func.md5(page_url),
                Highlight.page_url == page_url,
            )
        return await paginate(
            db,
            q.order_by(Highlight.created_at.desc(), Highlight.id),
            HIGHLIGHT_FIELDS,
            page,
            page_size,
        )


async def delete_highlight(principal: Principal, entity_id: UUID) -> None:
    """Create a versioned tombstone rather than losing remote delete information."""
    async with transaction() as db:
        stamp = await sync_stamp(db, principal.user_id)
        row = await owned(
            db, Highlight, entity_id, principal.user_id, "HIGHLIGHT_NOT_FOUND", True
        )
        row.is_deleted = True
        row.version += 1
        row.updated_at = stamp
