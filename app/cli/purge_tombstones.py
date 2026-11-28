"""Physically purge expired sync tombstones after the documented retention window."""

import argparse
import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select, union

from app.core.database import engine, transaction
from app.core.logging import configure_logging
from app.core.security import utcnow
from app.models.conversation import Conversation
from app.models.highlight import Highlight
from app.services.common import sync_stamp


async def purge(days: int) -> None:
    """Take each affected user lock before deleting expired tombstones."""
    if days < 30:
        raise ValueError("Sync tombstones must be retained for at least 30 days")
    cutoff = utcnow() - timedelta(days=days)
    total = 0
    try:
        while True:
            async with transaction() as db:
                users = (
                    await db.scalars(
                        union(
                            *[
                                select(model.user_id).where(
                                    model.is_deleted.is_(True),
                                    model.updated_at < cutoff,
                                )
                                for model in (Conversation, Highlight)
                            ]
                        ).limit(100)
                    )
                ).all()
            if not users:
                break
            for uid in sorted(users):
                async with transaction() as db:
                    await sync_stamp(db, uid)
                    for model in (Conversation, Highlight):
                        result = await db.execute(
                            delete(model)
                            .where(
                                model.user_id == uid,
                                model.is_deleted.is_(True),
                                model.updated_at < cutoff,
                            )
                            .returning(model.id)
                        )
                        total += len(result.all())
        logging.getLogger(__name__).info("tombstones_purged rows=%d", total)
    finally:
        await engine.dispose()


def main() -> None:
    """Purge only when explicitly invoked by an operator or scheduled job."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()
    asyncio.run(purge(args.days))


if __name__ == "__main__":
    main()
