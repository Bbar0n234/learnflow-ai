"""structlog processor factory for normalizing security events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import structlog
from siem_contracts import SecurityEvent, SecurityEventIdentifiers

from app.security_pipeline.transport import EventTransportHolder


def make_security_event_processor(
    holder: EventTransportHolder,
) -> structlog.types.Processor:
    """Build a structlog processor bound to the given transport holder.

    The processor:
    1. Checks for security_event=True marker
    2. Collects identifiers from contextvars (via merge_contextvars earlier in chain)
    3. Builds SecurityEvent Pydantic model
    4. Publishes to the transport from `holder` (non-blocking via bounded queue)
    5. Returns event_dict unchanged (other processors see it as-is)

    The transport is reached through the holder closure, so the processor can
    be wired into structlog before the transport is initialized.
    """

    def security_event_processor(
        logger: Any,
        method_name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        if not event_dict.get("security_event"):
            return event_dict

        try:
            event_type_str: str | None = event_dict.get("event_type")
            if not event_type_str:
                structlog.contextvars.bind_contextvars(
                    security_event_dropped="missing_event_type"
                )
                return event_dict

            event_id = event_dict.get("event_id")
            if isinstance(event_id, UUID):
                pass
            elif isinstance(event_id, str):
                try:
                    event_id = UUID(event_id)
                except (ValueError, TypeError):
                    event_id = uuid4()
            else:
                event_id = uuid4()

            level = str(event_dict.get("level") or method_name).lower()
            severity_map = {
                "debug": "info",
                "info": "info",
                "warning": "warning",
                "error": "critical",
                "critical": "critical",
                "exception": "critical",
            }
            severity = event_dict.get("severity", severity_map.get(level, "warning"))

            timestamp_str = event_dict.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    timestamp = datetime.now(timezone.utc)
            else:
                timestamp = datetime.now(timezone.utc)

            identifiers = SecurityEventIdentifiers(
                ip=event_dict.get("ip"),
                user_id=event_dict.get("user_id"),
                request_id=event_dict.get("request_id"),
                thread_id=event_dict.get("thread_id"),
                project_id=event_dict.get("project_id"),
                session_id=event_dict.get("session_id"),
                user_agent_hash=event_dict.get("user_agent_hash"),
            )

            metadata: dict[str, Any] = event_dict.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}

            known_fields = {
                "security_event",
                "event_type",
                "event_id",
                "severity",
                "timestamp",
                "level",
                "ip",
                "user_id",
                "request_id",
                "thread_id",
                "project_id",
                "session_id",
                "user_agent_hash",
                "metadata",
                "event_logger",
                "event_lineno",
                "event_filename",
            }
            for key, value in event_dict.items():
                if (
                    key not in known_fields
                    and not key.startswith("_")
                    and key not in metadata
                ):
                    metadata[key] = value

            security_event = SecurityEvent(
                event_id=event_id,
                event_type=event_type_str,  # type: ignore[arg-type]
                severity=severity,
                timestamp=timestamp,
                identifiers=identifiers,
                metadata=metadata,
            )

            transport = holder.get()
            if transport is not None:
                transport.put_nowait(security_event)

        except Exception as e:
            structlog.contextvars.bind_contextvars(
                security_event_processor_error=str(type(e).__name__)
            )

        return event_dict

    return security_event_processor
