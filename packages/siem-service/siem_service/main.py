"""SIEM service main FastAPI application."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from fastapi import FastAPI

from siem_service.api.routes import router
from siem_service.config import Settings
from siem_service.db import close_db, init_db
from siem_service.subscriber import Subscriber
from siem_service.supervisor import supervised

logger = structlog.get_logger()

# Global references to manage cleanup
_subscriber_task: asyncio.Task[None] | None = None
_redis_client: redis.Redis | None = None


async def _subscriber_coro(redis_client: redis.Redis, settings: Settings) -> None:
    """Coroutine for subscriber task."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Create a separate engine for the subscriber to avoid connection pool issues
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        subscriber = Subscriber(redis_client, async_session_maker, settings)
        await subscriber.run()
    finally:
        await engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup and shutdown."""
    global _subscriber_task, _redis_client

    # Startup
    settings = Settings()
    logger.info("siem service starting", database_url=settings.database_url)

    # Initialize database
    await init_db(settings)
    logger.info("database initialized")

    # Initialize Redis
    _redis_client = await redis.from_url(settings.redis_url)
    await _redis_client.ping()  # type: ignore[misc]  # redis-py asyncio stubs incomplete
    logger.info("redis connected")

    # Start subscriber task with supervision
    if _redis_client is None:
        raise RuntimeError("Redis client not initialized")

    async def _make_subscriber_coro() -> None:
        await _subscriber_coro(_redis_client, settings)

    _subscriber_task = asyncio.create_task(
        supervised("subscriber", _make_subscriber_coro)
    )
    logger.info("subscriber task started")

    yield

    # Shutdown
    logger.info("siem service shutting down")

    # Cancel subscriber
    if _subscriber_task:
        _subscriber_task.cancel()
        try:
            await _subscriber_task
        except asyncio.CancelledError:
            logger.info("subscriber task cancelled")

    # Close Redis
    if _redis_client:
        await _redis_client.close()
        logger.info("redis closed")

    # Close database
    await close_db()
    logger.info("database closed")


app = FastAPI(title="SIEM Service", version="0.1.0", lifespan=lifespan)

# Include routes
app.include_router(router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
