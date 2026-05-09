"""Bootstrap operations for application startup."""

# TODO: Хотелось бы понимать, как текущий bootstrap работает. То есть у нас приложение стартует, да, соответственно нужно как-то иметь возможность создавать админов без того, чтобы вручную лазить в базу данных, правильно? Для этого мы должны, наверное, как-то там изначально при старте приложения их идентифицировать и давать им соответствующие права, правильно? Вопрос, как это работает сейчас. Ведь фактически, ну вот представим первый старт приложения. Ты, условно говоря, не можешь... То есть, допустим, ты стартуешь с чистого листа, правильно? У тебя никакого пользователя не создано. Соответственно, даже если ты указал правильный username, но пользователь, который пока что не создан, ты не можешь ему присвоить админские права, правильно? Но при этом как бы непонятно, как это работает сейчас. Неужели это нужно сначала запустить, у тебя bootstrap пройдет с ошибкой, ты должен создать пользователя, после этого перезапустить и уже bootstrap пройдет без ошибки? Так ли это работает сейчас и так далее? И какие есть варианты вообще движения, хотелось бы понимать. То есть я бы хотел эту всю картину пересмотреть и по возможности даже что-то где-то, может быть, подправить, если есть такая необходимость.

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
