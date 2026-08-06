"""Local fixtures for the skill-context REST scope.

The frozen backend ``app`` fixture builds a real ``create_app()`` but never runs
lifespan, so ``app.state`` is empty. The skill-context routes read three
collaborators off ``app.state``: the LangGraph ``store``, an optional
``security_guard``, and ``skill_names`` (the startup snapshot of the skill
library used for the ``in_library`` badge). Here we populate that state with an
in-memory store and a chosen library set, and expose an ``api_client`` bound to
the enriched app. Tests may override individual slots (e.g. set
``security_guard`` to ``StubGuard(INJECTION)``) before issuing a request.

Nothing here touches the frozen harness; ``configured_app`` *depends on* the root
``app`` fixture and mutates its ``state`` in place.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from langgraph.store.memory import InMemoryStore

# The skill library the routes see; a skill *not* in this set exercises the
# ``in_library=false`` badge for data that outlived its skill.
SKILL_LIBRARY = frozenset({"tech-article-writing", "meeting-summarizer"})


@pytest.fixture
def configured_app(app: FastAPI) -> FastAPI:
    """Root ``app`` with ``state`` populated for the skill-context routes."""
    app.state.store = InMemoryStore()
    app.state.security_guard = None
    app.state.skill_names = SKILL_LIBRARY
    return app


@pytest_asyncio.fixture
async def api_client(configured_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Authenticated async client over the state-enriched app."""
    transport = ASGITransport(app=configured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
