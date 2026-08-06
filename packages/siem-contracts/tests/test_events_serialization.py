"""SecurityEvent serialization and validation — the wire contract both sides obey.

The producer serializes with ``model_dump_json`` and the consumer reconstructs with
``model_validate``; these guard that the round trip is lossless and that the schema
rejects the inputs the consumer's poison-drop path relies on (bad severity, unknown
type, missing/!UUID id).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError
from siem_contracts import SecurityEvent, SecurityEventIdentifiers


def _event(**overrides: object) -> SecurityEvent:
    base: dict[str, object] = {
        "event_id": uuid4(),
        "event_type": "auth.login.failed",
        "severity": "warning",
        "timestamp": datetime.now(UTC),
    }
    base.update(overrides)
    return SecurityEvent.model_validate(base)


def test_security_event_round_trips_through_json() -> None:
    event = _event(
        identifiers=SecurityEventIdentifiers(ip="192.0.2.1", user_id="u-1"),
        metadata={"reason": "invalid_credentials", "attempt": 2},
    )

    restored = SecurityEvent.model_validate_json(event.model_dump_json())

    assert restored == event
    assert restored.event_id == event.event_id
    assert restored.identifiers.ip == "192.0.2.1"
    assert restored.metadata == {"reason": "invalid_credentials", "attempt": 2}


def test_identifiers_dump_excludes_none_fields() -> None:
    # EventWriter persists identifiers via model_dump(mode="json", exclude_none=True);
    # only set keys must survive so JSONB stays sparse.
    event = _event(identifiers=SecurityEventIdentifiers(ip="203.0.113.9"))

    dumped = event.identifiers.model_dump(mode="json", exclude_none=True)

    assert dumped == {"ip": "203.0.113.9"}


def test_missing_identifiers_and_metadata_default_to_empty() -> None:
    event = _event()

    assert event.identifiers == SecurityEventIdentifiers()
    assert event.metadata == {}


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(event_type="totally.unknown.type")


@pytest.mark.parametrize("severity", ["fatal", "low", "", "INFO"])
def test_invalid_severity_is_rejected(severity: str) -> None:
    with pytest.raises(ValidationError):
        _event(severity=severity)


def test_non_uuid_event_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _event(event_id="not-a-uuid")


def test_missing_required_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SecurityEvent.model_validate({"event_type": "auth.login.failed"})
