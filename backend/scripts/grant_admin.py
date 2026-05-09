"""Grant admin privileges to an existing user.

Promotion is a deliberate action, never an automatic side-effect of startup.
Run after the target user has registered through the normal auth flow.

Usage: make grant-admin USER=<username>
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import Settings
from app.infra.db import create_engine, create_session_factory
from app.models.user import User
from sqlalchemy import select, update


async def grant_admin(username: str) -> int:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        user = (
            await session.execute(select(User).where(User.name == username))
        ).scalar_one_or_none()

        if user is None:
            print(f"User '{username}' not found. Register first, then grant admin.")
            return 1

        if getattr(user, "is_admin", False):
            print(f"User '{username}' is already an admin.")
            return 0

        await session.execute(
            update(User).where(User.id == user.id).values(is_admin=True)
        )
        await session.commit()
        print(f"User '{username}' granted admin privileges.")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant admin privileges to a user.")
    parser.add_argument("username", help="Username (User.name) of the target user.")
    args = parser.parse_args()

    sys.exit(asyncio.run(grant_admin(args.username)))


if __name__ == "__main__":
    main()
