"""Cross-side contract — the consumer half (siem-service).

Producer and consumer share one vocabulary by both importing the installed
``siem_contracts`` package. The structural guarantee this file owns is the one
checkable from *inside* the siem-service environment: that the consumer's
parse/write code binds to the *same* ``SecurityEvent`` object as the contract
package, not a forked copy.

The other halves of the cross-side contract live where they have teeth:

- **Producer ⊆ vocabulary** (every event type the backend actually emits is in
  the vocabulary, resolving variables/selectors/helper params) is asserted in the
  backend package, where ``app`` imports — see
  ``backend/tests/security/test_event_vocabulary_contract.py``. From the
  siem-service env ``app`` is not importable, so a source AST scan here could only
  see string literals and would pass vacuously (today every emit site passes a
  variable).
- **Wire round-trip** (the producer's exact serialized envelope parses on the
  consumer and lands in the DB) is asserted in
  ``test_subscriber_ingest.py::test_subscriber_consumes_producer_serialized_envelope``.
- **Literal ⇔ constants ⇔ __all__** vocabulary integrity is asserted in the
  ``siem_contracts`` library tests.

A per-vocabulary-type ``SecurityEvent`` validation test used to live here; it was
tautological (``SecurityEvent.event_type`` *is* the ``EventType`` Literal, so it
restates the vocabulary against itself) and was removed.
"""

from __future__ import annotations

import siem_contracts
from siem_contracts import SecurityEvent
from siem_service.pipeline import event_writer, subscriber


def test_consumer_uses_shared_contract_object_not_a_fork() -> None:
    # Both consumer modules must resolve SecurityEvent to the contract package.
    # Read via the module namespace (vars) because these are re-exported imports,
    # not the modules' own declared symbols. If a consumer ever forked its own
    # SecurityEvent, this identity check breaks while duck-typed tests stay green.
    assert vars(subscriber)["SecurityEvent"] is SecurityEvent
    assert vars(event_writer)["SecurityEvent"] is SecurityEvent
    assert SecurityEvent is siem_contracts.SecurityEvent
