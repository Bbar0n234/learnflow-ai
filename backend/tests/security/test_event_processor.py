"""Security-event processor: structlog event_dict -> SecurityEvent -> transport.

The processor only acts on ``security_event=True`` entries, normalizes them into
a ``SecurityEvent`` and hands them to the transport from the holder closure. We
spy the transport (publishing is its external contract) and assert which entries
produce an event and how fields land — passthrough is always preserved.
"""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from app.security_pipeline.processor import make_security_event_processor
from app.security_pipeline.transport import EventTransportHolder, RedisEventTransport
from siem_contracts import SecurityEvent

_EVENT_TYPE = "agent.guard.input.classifier_injection"


class _SpyTransport:
    def __init__(self) -> None:
        self.published: list[SecurityEvent] = []

    def put_nowait(self, event: SecurityEvent) -> None:
        self.published.append(event)


class _SpyHolder:
    def __init__(self, transport: _SpyTransport | None) -> None:
        self._transport = transport

    def get(self) -> RedisEventTransport | None:
        return cast(RedisEventTransport, self._transport)


def _processor(transport: _SpyTransport | None) -> object:
    holder = cast(EventTransportHolder, _SpyHolder(transport))
    return make_security_event_processor(holder)


@pytest.mark.unit
def test_processor_publishes_security_event() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {
        "security_event": True,
        "event_type": _EVENT_TYPE,
        "user_id": "u-1",
        "metadata": {"checkpoint": "user_input"},
    }

    result = processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert result is event_dict  # passthrough preserved
    assert len(transport.published) == 1
    published = transport.published[0]
    assert published.event_type == _EVENT_TYPE
    assert published.identifiers.user_id == "u-1"
    assert published.metadata["checkpoint"] == "user_input"


@pytest.mark.unit
def test_processor_folds_extra_fields_into_metadata() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {
        "security_event": True,
        "event_type": _EVENT_TYPE,
        "detection_layer": "canary",  # extra, not a known field
    }

    processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert transport.published[0].metadata["detection_layer"] == "canary"


@pytest.mark.unit
def test_processor_ignores_non_security_events() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {"event": "ordinary log", "level": "info"}

    result = processor("logger", "info", event_dict)  # type: ignore[operator]

    assert result is event_dict
    assert transport.published == []


@pytest.mark.unit
def test_processor_drops_event_without_event_type() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {"security_event": True}

    processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert transport.published == []


@pytest.mark.unit
def test_processor_recovers_from_invalid_event_id() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {
        "security_event": True,
        "event_type": _EVENT_TYPE,
        "event_id": "not-a-uuid",
    }

    processor("logger", "warning", event_dict)  # type: ignore[operator]

    # A fresh UUID is generated rather than crashing.
    assert len(transport.published) == 1


@pytest.mark.unit
def test_processor_preserves_uuid_event_id() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_id = uuid.uuid4()
    event_dict = {
        "security_event": True,
        "event_type": _EVENT_TYPE,
        "event_id": event_id,
    }

    processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert transport.published[0].event_id == event_id


@pytest.mark.unit
def test_processor_parses_iso_timestamp() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {
        "security_event": True,
        "event_type": _EVENT_TYPE,
        "timestamp": "2026-06-22T10:30:00+00:00",
    }

    processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert transport.published[0].timestamp.isoformat() == "2026-06-22T10:30:00+00:00"


@pytest.mark.unit
def test_processor_coerces_non_dict_metadata_to_empty() -> None:
    transport = _SpyTransport()
    processor = _processor(transport)
    event_dict = {
        "security_event": True,
        "event_type": _EVENT_TYPE,
        "metadata": "not-a-dict",
    }

    processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert transport.published[0].metadata == {}


@pytest.mark.unit
def test_processor_survives_transport_failure() -> None:
    class _ExplodingTransport:
        def put_nowait(self, event: SecurityEvent) -> None:
            raise RuntimeError("queue exploded")

    holder = cast(
        EventTransportHolder, _SpyHolder(cast("_SpyTransport", _ExplodingTransport()))
    )
    processor = make_security_event_processor(holder)
    event_dict = {"security_event": True, "event_type": _EVENT_TYPE}

    # A transport blow-up must never break the logging pipeline; passthrough holds.
    result = processor("logger", "warning", event_dict)

    assert result is event_dict


@pytest.mark.unit
def test_processor_without_transport_does_not_crash() -> None:
    processor = _processor(None)
    event_dict = {"security_event": True, "event_type": _EVENT_TYPE}

    result = processor("logger", "warning", event_dict)  # type: ignore[operator]

    assert result is event_dict
