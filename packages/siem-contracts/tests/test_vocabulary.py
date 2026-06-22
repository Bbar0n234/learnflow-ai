"""Integrity guards for the security-event vocabulary — the single source of truth.

The vocabulary is duplicated by construction: each event type lives both as a
module-level ``UPPER = "domain.subject.outcome"`` constant and as a member of the
``EventType`` ``Literal``, and is re-exported from the package ``__init__``. These
guards keep the three in lockstep so neither side of the producer/consumer border
can drift against a stale half of the definition.
"""

from __future__ import annotations

import re
from typing import get_args

import pytest
import siem_contracts
from siem_contracts.vocabulary import EventType

_LITERAL_VALUES = get_args(EventType)
_NAMING_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2,}$")


def _constant_items() -> dict[str, str]:
    """Module-level UPPERCASE string constants in the vocabulary module."""
    return {
        name: value
        for name, value in vars(siem_contracts.vocabulary).items()
        if name.isupper() and isinstance(value, str)
    }


def test_event_type_literal_matches_module_constants_exactly() -> None:
    # The Literal and the constants must describe the same set — a type added to
    # one but not the other is the canonical vocabulary drift.
    assert set(_LITERAL_VALUES) == set(_constant_items().values())


def test_event_type_literal_has_no_duplicate_members() -> None:
    assert len(_LITERAL_VALUES) == len(set(_LITERAL_VALUES))


def test_vocabulary_constants_have_no_duplicate_values() -> None:
    values = list(_constant_items().values())
    assert len(values) == len(set(values))


@pytest.mark.parametrize("value", sorted(set(_LITERAL_VALUES)))
def test_event_type_follows_hierarchical_naming(value: str) -> None:
    # Convention: <domain>.<subject>.<outcome> (three or more dotted segments).
    assert _NAMING_RE.match(value), value


@pytest.mark.parametrize("name", sorted(_constant_items()))
def test_every_constant_is_re_exported_from_package(name: str) -> None:
    # Each vocabulary constant must be part of the package public API so both
    # producer and consumer can import it from `siem_contracts` directly.
    assert name in siem_contracts.__all__
    assert getattr(siem_contracts, name) == _constant_items()[name]


def test_event_type_alias_is_re_exported() -> None:
    assert "EventType" in siem_contracts.__all__
    assert siem_contracts.EventType is EventType
