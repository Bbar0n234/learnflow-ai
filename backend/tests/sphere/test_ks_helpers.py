"""Solitary-unit tests for Knowledge Sphere pure helpers (S6).

``fuzzy_find_and_replace`` (the fuzzy-patch core), ``format_index`` (store items
-> system-message index), and the namespace/key builders are pure functions with
no I/O, so they are tested directly without dubles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from app.agent.tools.ks_helpers import (
    build_namespace,
    format_index,
    fuzzy_find_and_replace,
    section_key,
)
from app.agent.tools.store_helpers import format_index as generic_format_index

pytestmark = pytest.mark.unit


@dataclass
class _Item:
    key: str
    value: dict[str, Any]
    created_at: int


# --- namespace / key --------------------------------------------------------


def test_build_namespace_scopes_by_project() -> None:
    assert build_namespace("proj-7") == ("project", "proj-7", "sphere")


def test_section_key_prefixes_section() -> None:
    assert section_key("outline") == "section:outline"


# --- fuzzy_find_and_replace -------------------------------------------------


def test_fuzzy_short_target_exact_match_replaces() -> None:
    new_doc, success, found, sim = fuzzy_find_and_replace("abc def", "abc", "XYZ")

    assert success is True
    assert new_doc == "XYZ def"
    assert found == "abc"
    assert sim == 1.0


def test_fuzzy_short_target_no_match_returns_unchanged() -> None:
    new_doc, success, found, sim = fuzzy_find_and_replace("abc def", "zzz", "XYZ")

    assert success is False
    assert new_doc == "abc def"
    assert found is None
    assert sim == 0.0


def test_fuzzy_long_target_near_match_replaces() -> None:
    document = "the quick brown fox jumps over the lazy dog"
    # One typo within the target ("quikc") — within adaptive edit distance.
    new_doc, success, found, sim = fuzzy_find_and_replace(
        document, "the quikc brown fox", "A CAT"
    )

    assert success is True
    assert new_doc == "A CAT jumps over the lazy dog"
    assert 0.0 < sim < 1.0


def test_fuzzy_long_target_too_different_fails() -> None:
    document = "the quick brown fox jumps over the lazy dog"
    new_doc, success, _found, sim = fuzzy_find_and_replace(
        document, "completely unrelated sentence", "X"
    )

    assert success is False
    assert new_doc == document
    assert sim == 0.0


@pytest.mark.parametrize(
    ("document", "target"),
    [("", "target"), ("document", ""), ("", "")],
)
def test_fuzzy_empty_inputs_return_unchanged(document: str, target: str) -> None:
    new_doc, success, found, sim = fuzzy_find_and_replace(document, target, "X")

    assert success is False
    assert new_doc == document
    assert found is None
    assert sim == 0.0


# --- format_index -----------------------------------------------------------


def test_format_index_empty_returns_empty_label() -> None:
    assert format_index([]) == "Knowledge Sphere: empty"


def test_format_index_sorts_by_created_at_and_strips_prefix() -> None:
    items = [
        _Item("section:beta", {"description": "B desc"}, created_at=2),
        _Item("section:alpha", {"description": "A desc"}, created_at=1),
    ]

    result = format_index(items)

    assert result == ("Knowledge Sphere:\n- alpha: A desc\n- beta: B desc")


def test_generic_format_index_uses_raw_key_without_key_fn() -> None:
    items = [_Item("raw-key", {"description": "d"}, created_at=1)]

    result = generic_format_index(items, title="Memory")

    assert result == "Memory:\n- raw-key: d"
