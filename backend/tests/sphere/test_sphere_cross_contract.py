"""Cross-contract: agent tools write/read the same Knowledge Sphere as REST (S6).

Two code paths reach the same project memory: the agent tools
(``app.agent.tools.knowledge_sphere`` via ``ks_helpers.build_namespace`` /
``section_key``) and ``LangGraphSphereService`` (which inlines its own namespace
and ``"section:<id>"`` key in ``sphere.py``). Nothing forces those two
conventions to agree — drift in either the namespace tuple or the key prefix
would silently split project memory in half (a tool write the REST read can no
longer see, or vice versa).

These sociable tests run both collaborators over one shared ``InMemoryStore`` and
assert the round-trip across the seam: a tool write is visible to a service read,
and a service write is visible to a tool read. They go red the moment the two
namespace/key builders diverge.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any, cast

import pytest
from app.agent.graph import AgentContext
from app.agent.tools.knowledge_sphere import create_section, get_section
from app.services.sphere import LangGraphSphereService
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

pytestmark = pytest.mark.unit

_ToolCoro = Callable[..., Awaitable[str]]


def _coro(tool: object) -> _ToolCoro:
    return cast(_ToolCoro, cast(StructuredTool, tool).coroutine)


_create = _coro(create_section)
_get = _coro(get_section)


@pytest.fixture
def store() -> BaseStore:
    return InMemoryStore()


def _runtime(store: BaseStore, project_id: uuid.UUID) -> ToolRuntime[AgentContext, Any]:
    context = AgentContext(project_id=str(project_id), user_id="user-1")
    return ToolRuntime(
        state={},
        context=context,
        config={},
        stream_writer=lambda _: None,
        tool_call_id=None,
        store=store,
    )


async def test_tool_write_is_visible_to_service_read(store: BaseStore) -> None:
    project_id = uuid.uuid4()
    runtime = _runtime(store, project_id)
    service = LangGraphSphereService(store=store)

    await _create(
        section_id="goals",
        description="aims",
        content="ship the talk",
        runtime=runtime,
    )

    data = await service.get(project_id=project_id)

    # The REST service renders the tool-written section verbatim — same namespace,
    # same key.
    assert "## goals" in data.content
    assert "_aims_" in data.content
    assert "ship the talk" in data.content


async def test_service_write_is_visible_to_tool_read(store: BaseStore) -> None:
    project_id = uuid.uuid4()
    runtime = _runtime(store, project_id)
    service = LangGraphSphereService(store=store)

    await service.update(
        project_id=project_id, content="## Plan\n\n_p_\n\nthe plan body"
    )

    # The tool reads back exactly what the service persisted under the slugified
    # section id.
    result = await _get(section_id="plan", runtime=runtime)

    assert result == "the plan body"


async def test_tool_and_service_share_project_isolation(store: BaseStore) -> None:
    # A tool write under project A must not leak into a service read of project B:
    # the shared namespace builder keys both paths by project_id.
    project_a, project_b = uuid.uuid4(), uuid.uuid4()
    service = LangGraphSphereService(store=store)

    await _create(
        section_id="secret",
        description="d",
        content="alpha-only",
        runtime=_runtime(store, project_a),
    )

    assert "alpha-only" in (await service.get(project_id=project_a)).content
    assert (await service.get(project_id=project_b)).content == ""
