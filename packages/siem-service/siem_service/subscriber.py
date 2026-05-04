"""Redis Streams subscriber for security event ingestion."""

import asyncio
import json
from collections import defaultdict
from typing import Any

import redis.asyncio as redis
import structlog
from pydantic import ValidationError
from siem_contracts import SecurityEvent

from siem_service.config import Settings
from siem_service.event_writer import EventWriter

logger = structlog.get_logger()


class Subscriber:
    """Subscribes to Redis Streams and ingests security events."""

    STREAM_NAME = "security.events"
    CONSUMER_GROUP = "siem-readers"

    def __init__(
        self,
        redis_client: redis.Redis,
        session_factory: Any,
        settings: Settings,
        consumer_name: str = "siem-consumer-0",
    ) -> None:
        """Initialize subscriber.

        Args:
            redis_client: Redis async client
            session_factory: AsyncSession factory (async session maker)
            settings: SIEM settings
            consumer_name: Consumer name in the group
        """
        self._redis = redis_client
        self._session_factory = session_factory
        self._settings = settings
        self._consumer_name = consumer_name
        self._metrics: dict[str, int] = defaultdict(int)

    async def ensure_consumer_group(self) -> None:
        """Create consumer group if it doesn't exist (idempotent via MKSTREAM)."""
        try:
            await self._redis.xgroup_create(
                self.STREAM_NAME,
                self.CONSUMER_GROUP,
                id="$",
                mkstream=True,
            )
            logger.info(
                "created consumer group",
                stream=self.STREAM_NAME,
                group=self.CONSUMER_GROUP,
            )
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "consumer group already exists",
                    stream=self.STREAM_NAME,
                    group=self.CONSUMER_GROUP,
                )
            else:
                raise

    async def run(self) -> None:
        """Main subscriber loop: XREADGROUP → validate → INSERT → XACK."""
        await self.ensure_consumer_group()

        logger.info(
            "subscriber starting",
            stream=self.STREAM_NAME,
            group=self.CONSUMER_GROUP,
            consumer=self._consumer_name,
        )

        last_id: str | int = ">"  # Read new messages

        while True:
            try:
                # Read pending messages first (on restart)
                if last_id == ">":
                    pending = await self._read_pending()
                    if pending:
                        await self._process_messages_list(pending)

                # Read new messages
                messages = await self._read_group(last_id)
                if messages:
                    await self._process_messages_list(messages)

            except asyncio.CancelledError:
                logger.info("subscriber cancelled")
                raise
            except Exception:
                logger.exception("error in subscriber loop")
                raise

    async def _read_pending(self) -> list[tuple[str, dict[str, Any]]]:
        """Read unacknowledged messages from pending list."""
        try:
            # Read with ID "0" to get pending messages
            result = await self._redis.xreadgroup(
                groupname=self.CONSUMER_GROUP,
                consumername=self._consumer_name,
                streams={self.STREAM_NAME: "0"},
                count=self._settings.xread_batch_size,
            )
            if not result:
                return []

            messages: list[tuple[str, dict[str, Any]]] = []
            for _stream_key, stream_messages in result:
                for msg_id, msg_data in stream_messages:
                    messages.append((msg_id, msg_data))

            if messages:
                logger.info("processing pending messages", count=len(messages))
            return messages
        except redis.ResponseError:
            logger.warning("failed to read pending messages")
            return []

    async def _read_group(self, last_id: str | int) -> list[tuple[str, dict[str, Any]]]:
        """Read from consumer group with timeout."""
        result = await self._redis.xreadgroup(
            groupname=self.CONSUMER_GROUP,
            consumername=self._consumer_name,
            streams={self.STREAM_NAME: last_id},
            count=self._settings.xread_batch_size,
            block=self._settings.xread_block_ms,
        )

        if not result:
            return []

        messages: list[tuple[str, dict[str, Any]]] = []
        for _stream_key, stream_messages in result:
            for msg_id, msg_data in stream_messages:
                messages.append((msg_id, msg_data))

        return messages

    async def _process_messages_list(
        self, messages: list[tuple[str, dict[str, Any]]]
    ) -> None:
        """Process messages from stream."""
        for message_id, payload_dict in messages:
            await self._process_single_message(message_id, payload_dict)

    async def _process_single_message(
        self, message_id: str, payload_dict: dict[str, Any]
    ) -> None:
        """Process a single message: validate, write, ack."""
        event_id_str = str(payload_dict.get("event_id", "unknown"))

        try:
            # Parse JSON payload
            data_json = payload_dict.get("data", "{}")
            if isinstance(data_json, bytes):
                data_json = data_json.decode("utf-8")

            event_dict = json.loads(data_json)

            # Validate with SecurityEvent (strict)
            try:
                event = SecurityEvent.model_validate(event_dict)
            except ValidationError:
                self._metrics["siem_events_invalid"] += 1
                logger.warning(
                    "validation error on security event",
                    event_id=event_id_str,
                    raw_payload=data_json[:500],  # Truncate for logging
                )
                # XACK to prevent redelivery loop
                await self._redis.xack(
                    self.STREAM_NAME, self.CONSUMER_GROUP, message_id
                )
                return

            # Check for unknown event_type (vocabulary-soft mode)
            if not self._is_known_event_type(event.event_type):
                self._metrics["siem_unknown_event_type"] += 1
                logger.warning(
                    "unknown event type (accepting in soft mode)",
                    event_id=event_id_str,
                    event_type=event.event_type,
                )

            # Write to database
            async with self._session_factory() as session:
                writer = EventWriter(session)
                is_new = await writer.write(event)
                self._metrics["siem_events_ingested"] += 1
                if not is_new:
                    self._metrics["siem_events_duplicate"] += 1

            # Acknowledge after successful write
            await self._redis.xack(self.STREAM_NAME, self.CONSUMER_GROUP, message_id)

        except Exception:
            logger.exception(
                "error processing message",
                message_id=message_id,
                event_id=event_id_str,
            )
            self._metrics["siem_processing_errors"] += 1
            # XACK anyway to prevent infinite redelivery
            await self._redis.xack(self.STREAM_NAME, self.CONSUMER_GROUP, message_id)

    def _is_known_event_type(self, event_type: str) -> bool:
        """Check if event_type is in known vocabulary.

        For T2, accept all types (vocabulary-soft mode).
        """
        return True

    def get_metrics(self) -> dict[str, int]:
        """Return current metrics."""
        return dict(self._metrics)
