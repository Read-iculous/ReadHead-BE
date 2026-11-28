"""Resume-safe ciphertext migration after every writer has switched to the new key."""

import argparse
import asyncio
import logging

from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.database import engine, transaction
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.core.security import decrypt_secret, encrypt_secret
from app.models.api_key import UserApiKey


async def rotate(old: str, new: str) -> None:
    """Re-encrypt bounded batches without overwriting concurrent user replacements."""
    cfg = get_settings()
    if (
        old == new
        or old not in cfg.keyring
        or new not in cfg.keyring
        or cfg.current_key_version != new
    ):
        raise ValueError("Load both keys and switch all writers to --new-version first")
    count = 0
    skipped: list[str] = []
    try:
        while True:
            async with transaction() as db:
                query = (
                    select(UserApiKey.id, UserApiKey.encrypted_key)
                    .where(UserApiKey.encrypted_key.startswith(old + ":"))
                    .order_by(UserApiKey.id)
                    .limit(100)
                )
                if skipped:
                    query = query.where(UserApiKey.id.not_in(skipped))
                rows = (await db.execute(query)).all()
            if not rows:
                break
            replacements = []
            for row in rows:
                try:
                    replacements.append(
                        (
                            row.id,
                            row.encrypted_key,
                            encrypt_secret(decrypt_secret(row.encrypted_key), new),
                        )
                    )
                except AppException:
                    skipped.append(row.id)
                    logging.getLogger(__name__).error(
                        "vault_rotation_skipped row=%s reason=undecryptable", row.id
                    )
            if not replacements:
                break
            async with transaction() as db:
                for uid, before, after in replacements:
                    result = await db.execute(
                        update(UserApiKey)
                        .where(UserApiKey.id == uid, UserApiKey.encrypted_key == before)
                        .values(encrypted_key=after)
                        .returning(UserApiKey.id)
                    )
                    count += result.scalar_one_or_none() is not None
        logging.getLogger(__name__).info("vault_rotation_completed rows=%d", count)
    finally:
        await engine.dispose()


def main() -> None:
    """Use version labels only; secrets stay in environment keyrings."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old-version", required=True)
    parser.add_argument("--new-version", required=True)
    args = parser.parse_args()
    asyncio.run(rotate(args.old_version, args.new_version))


if __name__ == "__main__":
    main()
