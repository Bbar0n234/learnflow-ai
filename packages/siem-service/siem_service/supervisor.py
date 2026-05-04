"""Background task supervisor with exponential backoff restart logic."""

import asyncio
from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger()


async def supervised(
    name: str,
    coro_factory: Callable[[], Awaitable[None]],
    max_backoff: float = 60.0,
) -> None:
    """Supervise a background coroutine with exponential backoff on failure.

    Restarts the coroutine indefinitely with exponential backoff (1s → max_backoff).
    Catches all exceptions except CancelledError (which triggers graceful stop).

    Args:
        name: Task name for logging
        coro_factory: Callable that creates the coroutine to run
        max_backoff: Maximum backoff time in seconds (default 60)
    """
    backoff = 1.0
    while True:
        try:
            logger.info("starting supervised task", task=name)
            await coro_factory()
            logger.info("supervised task completed normally", task=name)
            backoff = 1.0
        except asyncio.CancelledError:
            logger.info("supervised task cancelled, stopping", task=name)
            raise
        except Exception:
            logger.exception(
                "supervised task crashed, restarting with backoff",
                task=name,
                backoff_seconds=backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
