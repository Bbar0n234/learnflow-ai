"""Cross-side contract: emitter (main app) and consumer (siem-service) share one
vocabulary.

The drift this guards: one side starts speaking event types the other does not
know. The mechanism is structural — both sides ``from siem_contracts import ...``
the same installed package — but structure rots silently, so we assert it three
ways:

1. The consumer's parse/write code references the *same* ``SecurityEvent`` object
   as the contract package (no forked copy).
2. Every event type in the canonical vocabulary validates as a ``SecurityEvent``
   (the consumer's only gate), so the consumer recognizes the full producer set.
3. The emitter (backend) draws its event types from ``siem_contracts`` and
   hardcodes none — checked by reading the emitter source, since the backend
   package is not importable from the siem-service test environment.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args
from uuid import uuid4

import pytest
import siem_contracts
from siem_contracts import SecurityEvent
from siem_contracts.vocabulary import EventType
from siem_service.pipeline import event_writer, subscriber

_REPO_ROOT = Path(__file__).resolve().parents[4]
# Backend emitter modules that pass event_type= when logging security events.
_EMITTER_FILES = (
    _REPO_ROOT / "backend" / "app" / "api" / "routes" / "auth.py",
    _REPO_ROOT / "backend" / "app" / "agent" / "security" / "guard.py",
)
_VOCAB_VALUES = frozenset(get_args(EventType))


def _vocab_constant_names() -> set[str]:
    """UPPERCASE event-type string constants declared in the vocabulary module."""
    return {
        name
        for name, value in vars(siem_contracts.vocabulary).items()
        if name.isupper() and isinstance(value, str)
    }


def test_consumer_uses_shared_contract_object_not_a_fork() -> None:
    # Both consumer modules must resolve SecurityEvent to the contract package.
    # Read via the module namespace (vars) because these are re-exported imports,
    # not the modules' own declared symbols.
    assert vars(subscriber)["SecurityEvent"] is SecurityEvent
    assert vars(event_writer)["SecurityEvent"] is SecurityEvent
    assert SecurityEvent is siem_contracts.SecurityEvent


@pytest.mark.parametrize("event_type", sorted(_VOCAB_VALUES))
def test_every_vocabulary_type_is_accepted_by_consumer_validation(
    event_type: str,
) -> None:
    # SecurityEvent is the consumer's sole acceptance gate (subscriber validates
    # against it). Every producer-vocabulary type must pass it.
    event = SecurityEvent(
        event_id=uuid4(),
        event_type=event_type,  # type: ignore[arg-type]
        severity="info",
        timestamp=datetime.now(UTC),
    )
    assert event.event_type == event_type


@pytest.mark.parametrize("emitter_file", _EMITTER_FILES, ids=lambda p: p.name)
def test_emitter_hardcodes_no_event_type_outside_vocabulary(
    emitter_file: Path,
) -> None:
    # A literal passed as event_type=... that is not in the shared vocabulary is
    # exactly the cross-side drift this catches (today there are none — emitters
    # use imported constants — so this stays green until someone hardcodes one).
    tree = ast.parse(emitter_file.read_text(encoding="utf-8"))
    hardcoded = {
        node.value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        for node in (kw.value for kw in call.keywords if kw.arg == "event_type")
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert hardcoded <= _VOCAB_VALUES, (
        f"{emitter_file.name} hardcodes event types outside the vocabulary: "
        f"{hardcoded - _VOCAB_VALUES}"
    )


@pytest.mark.parametrize("emitter_file", _EMITTER_FILES, ids=lambda p: p.name)
def test_emitter_draws_event_type_constants_from_shared_vocabulary(
    emitter_file: Path,
) -> None:
    # Names the emitter imports `from siem_contracts` that look like event-type
    # constants must resolve, in the contract package, to real vocabulary values.
    # Catches a producer that forks the constants into its own module.
    tree = ast.parse(emitter_file.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "siem_contracts"
        for alias in node.names
    }
    vocab_names = _vocab_constant_names()
    imported_vocab = imported & vocab_names
    assert imported_vocab, f"{emitter_file.name} imports no vocabulary constants"
    for name in imported_vocab:
        value = getattr(siem_contracts, name)
        assert value in _VOCAB_VALUES
