"""SIEM service main FastAPI application."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import redis.asyncio as redis
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from siem_service.api.problem import problem_response, register_problem_handlers
from siem_service.api.routes import router
from siem_service.config import Settings
from siem_service.correlation.engine import CorrelationEngine
from siem_service.infra.auth import JWTValidator
from siem_service.infra.db import create_engine, create_session_factory
from siem_service.pipeline.meta_emitter import MetaEmitter
from siem_service.pipeline.subscriber import Subscriber
from siem_service.pipeline.supervisor import supervised

logger = structlog.get_logger()


async def _subscriber_coro(redis_client: redis.Redis, settings: Settings) -> None:
    """Coroutine for subscriber task."""
    # Create a separate engine for the subscriber to avoid connection pool issues
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    try:
        subscriber = Subscriber(redis_client, session_factory, settings)
        await subscriber.run()
    finally:
        await engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager for startup and shutdown."""
    settings: Settings = app.state.settings
    logger.info("siem service starting", database_url=settings.database_url)

    # Database
    engine = create_engine(settings)
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    logger.info("database initialized")

    # Redis
    redis_client = await redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    app.state.redis = redis_client
    logger.info("redis connected")

    # JWT validation + meta-event emitter (used by routes via Depends)
    app.state.jwt_validator = JWTValidator(settings.jwt_secret)
    app.state.meta_emitter = MetaEmitter(redis_client)

    # Subscriber task with supervision
    async def _make_subscriber_coro() -> None:
        await _subscriber_coro(redis_client, settings)

    subscriber_task = asyncio.create_task(
        supervised("subscriber", _make_subscriber_coro)
    )
    logger.info("subscriber task started")

    # Correlation engine task with supervision
    correlation_engine = CorrelationEngine(
        session_factory=app.state.session_factory,
        poll_interval_seconds=settings.poll_interval_seconds,
        alert_open_window_seconds=settings.alert_open_window_seconds,
    )

    engine_task = asyncio.create_task(
        supervised("correlation_engine", correlation_engine.start)
    )
    logger.info("correlation engine task started")

    yield

    # Shutdown
    logger.info("siem service shutting down")

    engine_task.cancel()
    with suppress(asyncio.CancelledError):
        await engine_task
    logger.info("correlation engine task cancelled")

    subscriber_task.cancel()
    with suppress(asyncio.CancelledError):
        await subscriber_task
    logger.info("subscriber task cancelled")

    await redis_client.aclose()
    logger.info("redis closed")

    await engine.dispose()
    logger.info("database closed")


def create_app() -> FastAPI:
    settings = Settings()
    app = FastAPI(title="SIEM Service", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings

    # Exception handlers — RFC 9457 problem+json
    register_problem_handlers(app)

    # CORS — allow frontend to access SIEM API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.frontend_origin,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Layer 3 — generic last-resort catch (CORS on 500).
    # This middleware sits below CORSMiddleware in the stack, so the
    # JSONResponse we return here passes back up through CORS and picks
    # up Access-Control-Allow-Origin headers, unlike a bare
    # add_exception_handler(Exception) which sits above CORS.
    @app.middleware("http")
    async def _generic_exception_middleware(request: Request, call_next: Any) -> Any:
        try:
            return await call_next(request)
        except Exception:
            logger.error("unhandled exception", exc_info=True)
            return problem_response(status=500)

    app.include_router(router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    return app


app = create_app()
