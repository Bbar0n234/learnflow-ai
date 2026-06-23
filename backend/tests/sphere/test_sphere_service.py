"""Sociable-unit tests for ``LangGraphSphereService`` (S6).

The service is exercised over a real in-memory LangGraph store (its true
collaborator) — no Postgres, no DB harness. We assert the *result* of get/update
(returned ``SphereData`` content), markdown section parsing, the delete-removed
behavior, and the guard reaction (INJECTION -> raise, CLEAN/SUSPICIOUS -> pass).
"""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, DetectionLayer, Verdict
from app.services.exceptions import SecurityPolicyViolationError
from app.services.sphere import (
    LangGraphSphereService,
    _parse_markdown_sections,
    _slugify,
)
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from learnflow_testing.fakes import StubGuard

pytestmark = pytest.mark.unit


@pytest.fixture
def store() -> BaseStore:
    return InMemoryStore()


async def test_get_on_empty_sphere_returns_blank_content(store: BaseStore) -> None:
    service = LangGraphSphereService(store=store)
    pid = uuid.uuid4()

    data = await service.get(project_id=pid)

    assert data.project_id == pid
    assert data.content == ""
    assert data.updated_at is not None


async def test_update_parses_markdown_into_sections(store: BaseStore) -> None:
    service = LangGraphSphereService(store=store)
    pid = uuid.uuid4()
    markdown = "## Goals\n\n_the aim_\n\nbody text here"

    data = await service.update(project_id=pid, content=markdown)

    # Header slugified, description and body preserved through store round-trip.
    assert "## goals" in data.content
    assert "_the aim_" in data.content
    assert "body text here" in data.content


async def test_update_persists_multiple_sections_sorted(store: BaseStore) -> None:
    service = LangGraphSphereService(store=store)
    pid = uuid.uuid4()
    markdown = "## First\n\n_a_\n\none\n\n## Second\n\n_b_\n\ntwo"

    data = await service.update(project_id=pid, content=markdown)

    assert "## first" in data.content
    assert "## second" in data.content
    assert data.content.index("first") < data.content.index("second")


async def test_update_replacing_content_deletes_removed_sections(
    store: BaseStore,
) -> None:
    service = LangGraphSphereService(store=store)
    pid = uuid.uuid4()
    await service.update(
        project_id=pid, content="## Keep\n\n_k_\n\nkeep\n\n## Drop\n\n_d_\n\ndrop"
    )

    data = await service.update(project_id=pid, content="## Keep\n\n_k_\n\nupdated")

    assert "updated" in data.content
    assert "drop" not in data.content.lower()


async def test_update_isolates_projects_by_namespace(store: BaseStore) -> None:
    service = LangGraphSphereService(store=store)
    pid_a, pid_b = uuid.uuid4(), uuid.uuid4()

    await service.update(project_id=pid_a, content="## A\n\n_a_\n\nalpha")
    data_a = await service.get(project_id=pid_a)
    data_b = await service.get(project_id=pid_b)

    # The write landed under project A's namespace ...
    assert "alpha" in data_a.content
    # ... and is invisible from project B's namespace (true isolation, not just
    # an empty store).
    assert data_b.content == ""


@pytest.mark.parametrize(
    "detection_layer",
    [DetectionLayer.LLM_CLASSIFIER, DetectionLayer.UNICODE],
)
async def test_update_with_injection_verdict_raises_and_skips_write(
    store: BaseStore, detection_layer: DetectionLayer
) -> None:
    # A real guard that returns INJECTION always carries the detection layer that
    # produced the verdict (classifier or a detector); the service surfaces that
    # layer as the violation ``reason``. The ``"ks_write_rest"`` fallback only
    # fires when ``detection_layer is None`` — unreachable for a true INJECTION —
    # so the contract under test is ``reason == detection_layer.value``.
    guard = StubGuard(Verdict.INJECTION, detection_layer=detection_layer)
    service = LangGraphSphereService(store=store, guard=cast(SecurityGuard, guard))
    pid = uuid.uuid4()

    with pytest.raises(SecurityPolicyViolationError) as exc_info:
        await service.update(project_id=pid, content="## A\n\nmalicious")

    assert exc_info.value.status == 422
    assert exc_info.value.reason == detection_layer.value
    # The guard was consulted at the KS write checkpoint before any store write.
    assert guard.call_records[0]["checkpoint"] == Checkpoint.KS_WRITE_REST
    # Nothing was persisted: a subsequent read is empty.
    assert (await service.get(project_id=pid)).content == ""


@pytest.mark.parametrize("verdict", [Verdict.CLEAN, Verdict.SUSPICIOUS])
async def test_update_with_non_injection_verdict_persists(
    store: BaseStore, verdict: Verdict
) -> None:
    guard = StubGuard(verdict)
    service = LangGraphSphereService(store=store, guard=cast(SecurityGuard, guard))
    pid = uuid.uuid4()

    data = await service.update(project_id=pid, content="## A\n\n_d_\n\nallowed body")

    assert "allowed body" in data.content
    # The guard was consulted at the KS write checkpoint with the submitted body
    # before the write went through.
    assert len(guard.call_records) == 1
    record = guard.call_records[0]
    assert record["checkpoint"] == Checkpoint.KS_WRITE_REST
    assert "allowed body" in record["content"]


async def test_update_without_guard_persists(store: BaseStore) -> None:
    service = LangGraphSphereService(store=store, guard=None)
    pid = uuid.uuid4()

    data = await service.update(project_id=pid, content="## A\n\n_d_\n\nno guard body")

    assert "no guard body" in data.content


# --- _slugify (solitary unit, pure) -----------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Goals", "goals"),
        ("Talk Audience", "talk-audience"),  # spaces collapse to a single dash
        ("  Padded  ", "padded"),  # surrounding whitespace trimmed
        ("Q&A: notes!", "qa-notes"),  # punctuation stripped, not turned into dashes
        ("snake_case_id", "snake-case-id"),  # underscores normalized to dashes
        ("multi   space\ttab", "multi-space-tab"),  # runs of whitespace -> one dash
        ("--Leading/Trailing--", "leadingtrailing"),  # edge dashes stripped
    ],
)
def test_slugify_normalizes_spaces_and_special_chars(
    header: str, expected: str
) -> None:
    assert _slugify(header) == expected


# --- _parse_markdown_sections (solitary unit, pure) -------------------------


def test_parse_markdown_sections_uses_italic_line_as_description() -> None:
    sections = _parse_markdown_sections("## Goals\n\n_the aim_\n\nbody text")

    assert sections == [("goals", "the aim", "body text")]


def test_parse_markdown_sections_without_italic_falls_back_to_first_line() -> None:
    # No italic ``_..._`` description: the first body line becomes the
    # description (capped at 100 chars) and the remainder becomes the content.
    sections = _parse_markdown_sections("## Goals\n\nplain first line\nrest of body")

    assert sections == [("goals", "plain first line", "rest of body")]


def test_parse_markdown_sections_without_italic_single_line_has_empty_content() -> None:
    sections = _parse_markdown_sections("## Goals\n\nonly one line")

    assert sections == [("goals", "only one line", "")]
