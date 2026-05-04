"""Bootstrap operations for application startup."""

import os

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = structlog.get_logger()


async def bootstrap_admin(session: AsyncSession) -> None:
    """Bootstrap initial admin user if env variable is set.

    Args:
        session: Database session
    """
    initial_admin_username = os.getenv("INITIAL_ADMIN_USERNAME")

    if not initial_admin_username:
        logger.debug("no initial admin username configured")
        return

    # Find user by name (username field is called 'name' in the schema)
    stmt = select(User).where(User.name == initial_admin_username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        logger.warning(
            "initial_admin_user_not_found",
            username=initial_admin_username,
        )
        return

    # Update is_admin if not already set
    if not getattr(user, "is_admin", False):
        update_stmt = update(User).where(User.id == user.id).values(is_admin=True)
        await session.execute(update_stmt)
        await session.commit()
        logger.info(
            "admin_bootstrapped",
            username=initial_admin_username,
        )
    else:
        logger.debug(
            "admin_already_bootstrapped",
            username=initial_admin_username,
        )
