"""Meta-event emitter for SIEM administrative actions."""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

import redis.asyncio as redis
import structlog
from siem_contracts import EventType, SecurityEvent, SecurityEventIdentifiers

logger = structlog.get_logger()


class MetaEmitter:
    """Emits meta-events to Redis Stream."""

    def __init__(
        self, redis_client: redis.Redis, stream_name: str = "security.events"
    ) -> None:
        """Initialize emitter."""
        self.redis = redis_client
        self.stream_name = stream_name
        self._metrics: dict[str, int] = defaultdict(int)

    async def emit(
        self,
        event_type: EventType,
        severity: Literal["info", "warning", "critical"],
        user_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Emit a meta-event to Redis Stream."""
        if metadata is None:
            metadata = {}

        event = SecurityEvent(
            event_id=uuid4(),
            event_type=event_type,
            severity=severity,
            timestamp=datetime.now(UTC),
            identifiers=SecurityEventIdentifiers(user_id=user_id),
            metadata=metadata,
        )

        try:
            # XADD security.events with {"data": <event JSON>}; event_id is
            # embedded inside the JSON payload, not as a separate stream field.
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
        except Exception:
            self._metrics["meta_events_dropped"] += 1
            logger.error(
                "meta_event_emission_failed",
                event_type=event_type,
                exc_info=True,
            )
