"""Bootstrap an administrator without weakening public registration."""

import argparse
import asyncio
import getpass
import logging

from pydantic import SecretStr
from sqlalchemy import select

from app.core.database import engine, transaction
from app.core.logging import configure_logging
from app.core.security import hash_password
from app.models.user import User
from app.models.user_setting import UserSetting
from app.schemas.auth import UserRegisterRequest
from app.services.common import sync_stamp


async def create(email: str, password: str) -> None:
    """Create one new administrator and its initial synchronized preferences."""
    validated = UserRegisterRequest(
        email=email, password=SecretStr(password), full_name="Administrator"
    )
    hashed = await asyncio.to_thread(
        hash_password, validated.password.get_secret_value()
    )
    try:
        async with transaction() as db:
            if await db.scalar(select(User.id).where(User.email == validated.email)):
                raise ValueError(
                    "Account already exists; bootstrap does not silently elevate accounts"
                )
            user = User(
                email=validated.email,
                hashed_password=hashed,
                role="admin",
                is_verified=True,
                full_name=validated.full_name,
            )
            db.add(user)
            await db.flush()
            stamp = await sync_stamp(db, user.id)
            db.add(UserSetting(user_id=user.id, updated_at=stamp))
        logging.getLogger(__name__).info("administrator_created")
    finally:
        await engine.dispose()


def main() -> None:
    """Read CLI arguments; accept an interactive password if omitted."""
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password")
    args = parser.parse_args()
    asyncio.run(
        create(args.email, args.password or getpass.getpass("Administrator password: "))
    )


if __name__ == "__main__":
    main()
