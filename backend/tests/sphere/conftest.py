"""Local fixtures for the Knowledge Sphere scope (S6).

The REST endpoints resolve their service through ``get_sphere_service``, which in
production reads ``app.state.store`` — never populated under ``ASGITransport``
(lifespan does not run). So these fixtures override the provider with a real
``LangGraphSphereService`` backed by an in-memory LangGraph store: the handler ->
service -> store seam runs for real, only the persistent store is swapped for the
in-memory one. This keeps the REST tests sociable (real service logic) while
staying off the agent's Postgres-backed store.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
from app.agent.security.guard import SecurityGuard
from app.api.deps import get_sphere_service
from app.services.sphere import LangGraphSphereService
from fastapi import FastAPI
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore


@pytest.fixture
def sphere_store() -> BaseStore:
    """A fresh in-memory store shared by the overridden sphere service."""
    return InMemoryStore()


@pytest.fixture
def install_sphere_service(
    app: FastAPI, sphere_store: BaseStore
) -> Callable[..., BaseStore]:
    """Override ``get_sphere_service`` with a store-backed real service.

    Installed once with no guard by default; call the returned installer again to
    re-install with a guard (e.g. ``StubGuard(Verdict.INJECTION)``) for the
    security-policy path. Returns the shared store for direct inspection/seeding.
    """

    def _install(guard: object | None = None) -> BaseStore:
        app.dependency_overrides[get_sphere_service] = lambda: LangGraphSphereService(
            store=sphere_store, guard=cast("SecurityGuard | None", guard)
        )
        return sphere_store

    _install()
    return _install
