"""Meta-event emitter for SIEM administrative actions."""

from datetime import UTC, datetime
from uuid import uuid4

import redis.asyncio as redis
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class SecurityIdentifiers(BaseModel):
    """Security event identifiers."""

    user_id: str | None = None
    ip: str | None = None
    request_id: str | None = None
    thread_id: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    user_agent_hash: str | None = None


class SecurityEvent(BaseModel):
    """Meta-security event for SIEM administrative actions."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    severity: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    identifiers: SecurityIdentifiers
    metadata: dict = Field(default_factory=dict)


class MetaEmitter:
    """Emits meta-events to Redis Stream."""

    def __init__(
        self, redis_client: redis.Redis, stream_name: str = "security.events"
    ) -> None:
        """Initialize emitter."""
        self.redis = redis_client
        self.stream_name = stream_name

    async def emit(
        self,
        event_type: str,
        severity: str,
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Emit a meta-event to Redis Stream."""
        if metadata is None:
            metadata = {}

        event = SecurityEvent(
            event_type=event_type,
            severity=severity,
            identifiers=SecurityIdentifiers(user_id=user_id),
            metadata=metadata,
        )

        try:
            # XADD security.events with event_id as field to ensure idempotency
            await self.redis.xadd(
                self.stream_name,
                {
                    "data": event.model_dump_json(),
                },
            )
            logger.info(
                "meta_event_emitted",
                event_type=event_type,
                severity=severity,
                user_id=user_id,
            )
        except Exception as e:
            logger.error(
                "meta_event_emission_failed",
                event_type=event_type,
                error=str(e),
            )


_meta_emitter: MetaEmitter | None = None


def get_meta_emitter(redis_client: redis.Redis | None = None) -> MetaEmitter:
    """Get or create meta-emitter singleton.

    Args:
        redis_client: Async Redis client (required). Must not be None.

    Returns:
        MetaEmitter singleton instance

    Raises:
        ValueError: If redis_client is None (must be provided via dependency)
    """
    global _meta_emitter

    if _meta_emitter is None:
        if redis_client is None:
            raise ValueError(
                "redis_client must be provided to get_meta_emitter. "
                "Pass it as a FastAPI dependency."
            )

        _meta_emitter = MetaEmitter(redis_client)

    return _meta_emitter
