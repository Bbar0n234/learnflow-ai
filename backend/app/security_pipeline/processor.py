"""structlog processor for normalizing security events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import structlog
from siem_contracts import SecurityEvent, SecurityEventIdentifiers

from app.security_pipeline.transport import get_transport


def security_event_processor(
    logger: Any,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Normalize security events into SecurityEvent and publish to transport.

    This processor:
    1. Checks for security_event=True marker
    2. Collects identifiers from contextvars (via merge_contextvars earlier in chain)
    3. Builds SecurityEvent Pydantic model
    4. Publishes to transport (non-blocking via bounded queue)
    5. Returns event_dict unchanged (other processors see it as-is)

    Args:
        logger: structlog logger
        method_name: Method name (debug, info, warning, etc)
        event_dict: Log event dictionary

    Returns:
        Unchanged event_dict (only side-effect is publishing)
    """
    if not event_dict.get("security_event"):
        return event_dict

    try:
        # Extract event_type - producer should pass it explicitly
        event_type_str: str | None = event_dict.get("event_type")
        if not event_type_str:
            structlog.contextvars.bind_contextvars(
                security_event_dropped="missing_event_type"
            )
            return event_dict

        # Generate event_id if not provided
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

        # Get severity (default to log level or 'warning')
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

        # Extract timestamp (already in event_dict from TimeStamper)
        # event_dict should have "timestamp" from TimeStamper processor
        timestamp_str = event_dict.get("timestamp")
        if timestamp_str:
            try:
                # TimeStamper uses ISO format
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        # Build identifiers from contextvars (already extracted by merge_contextvars)
        identifiers = SecurityEventIdentifiers(
            ip=event_dict.get("ip"),
            user_id=event_dict.get("user_id"),
            request_id=event_dict.get("request_id"),
            thread_id=event_dict.get("thread_id"),
            project_id=event_dict.get("project_id"),
            session_id=event_dict.get("session_id"),
            user_agent_hash=event_dict.get("user_agent_hash"),
        )

        # Extract metadata - everything except known fields
        metadata: dict[str, Any] = event_dict.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        # Copy event-specific fields into metadata if they're not already there
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

        # Create SecurityEvent
        # Note: event_type_str is already validated as EventType by producer mypy
        security_event = SecurityEvent(
            event_id=event_id,
            event_type=event_type_str,  # type: ignore[arg-type]
            severity=severity,
            timestamp=timestamp,
            identifiers=identifiers,
            metadata=metadata,
        )

        # Publish to transport (non-blocking)
        transport = get_transport()
        if transport is not None:
            transport.put_nowait(security_event)

    except Exception as e:
        # On processor error, log warning but don't crash
        structlog.contextvars.bind_contextvars(
            security_event_processor_error=str(type(e).__name__)
        )

    return event_dict
