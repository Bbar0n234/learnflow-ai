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
from app.agent.security.types import Verdict
from app.services.exceptions import SecurityPolicyViolationError
from app.services.sphere import LangGraphSphereService
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
    data_b = await service.get(project_id=pid_b)

    # Project B sees nothing written under project A's namespace.
    assert data_b.content == ""


async def test_update_with_injection_verdict_raises_and_skips_write(
    store: BaseStore,
) -> None:
    guard = StubGuard(Verdict.INJECTION)
    service = LangGraphSphereService(store=store, guard=cast(SecurityGuard, guard))
    pid = uuid.uuid4()

    with pytest.raises(SecurityPolicyViolationError) as exc_info:
        await service.update(project_id=pid, content="## A\n\nmalicious")

    assert exc_info.value.status == 422
    assert exc_info.value.reason == "ks_write_rest"
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
    assert guard.calls  # the guard was consulted


async def test_update_without_guard_persists(store: BaseStore) -> None:
    service = LangGraphSphereService(store=store, guard=None)
    pid = uuid.uuid4()

    data = await service.update(project_id=pid, content="## A\n\n_d_\n\nno guard body")

    assert "no guard body" in data.content
