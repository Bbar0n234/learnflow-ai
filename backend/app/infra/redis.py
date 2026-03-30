from __future__ import annotations

import redis.asyncio as aioredis
import structlog

from app.config import Settings

logger = structlog.get_logger()


async def create_redis(settings: Settings) -> aioredis.Redis | None:
    """Create async Redis client with graceful degradation.

    Returns None if Redis is unavailable — the app works without it,
    but feedback trace mapping will be disabled.
    """
    if not settings.redis_url:
        logger.info("redis disabled, url not configured")
        return None

    try:
        client: aioredis.Redis = aioredis.from_url(settings.redis_url)
        await client.ping()  # type: ignore[misc]
        logger.info("redis connected")
        return client
    except Exception:
        logger.warning(
            "redis connection failed, proceeding without trace storage", exc_info=True
        )
        return None
