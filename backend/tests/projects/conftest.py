"""Local fixtures for the Projects scope (S4).

Adds ``ThreadViewFactory``, the one factory the shared ``learnflow_testing``
package does not ship (async-factory-boy, bound to the test's transactional
session). Bound per test by an autouse fixture that piggybacks on
``db_session`` (which the backend conftest already wires for the shared
factories).

``ArtifactFactory`` used to live here too (PG-backed artifacts, S4-era); it
was removed in T1.9 along with the `artifacts` table it modelled — artifacts
are files under a project's workspace now (ADR-032), not DB rows. What
replaces it for the artifacts/uploads endpoints is ``workspace``: a real file
layer on ``tmp_path`` roots, installed on ``app.state`` because that is where
``get_workspace`` reads it from and lifespan never runs under
``ASGITransport`` (same pattern the other ``app.state`` collaborators use).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.models.thread_view import ThreadView
from app.storage.workspace import Workspace
from async_factory_boy.factory.sqlalchemy import AsyncSQLAlchemyFactory

# Import from the defining submodule: factory/__init__ re-exports these without
# listing them in __all__, which trips mypy's no_implicit_reexport on
# ``factory.Sequence`` / ``factory.SubFactory``.
from factory.declarations import Sequence, SubFactory
from fastapi import FastAPI
from learnflow_testing.factories import ProjectFactory, bind_session
from sqlalchemy.ext.asyncio import AsyncSession


class ThreadViewFactory(AsyncSQLAlchemyFactory):
    class Meta:
        model = ThreadView
        sqlalchemy_session_persistence = "flush"

    title = Sequence(lambda n: f"thread-{n}")
    project = SubFactory(ProjectFactory)


@pytest.fixture(autouse=True)
def _bind_local_factories(db_session: AsyncSession) -> None:
    """Point the scope-local factories at the active transactional session."""
    bind_session(db_session, ThreadViewFactory)


@pytest.fixture
def workspaces_root(tmp_path: Path) -> Path:
    root = tmp_path / "workspaces"
    root.mkdir()
    return root


@pytest.fixture
def workspace(app: FastAPI, workspaces_root: Path, tmp_path: Path) -> Workspace:
    """Real file layer on throwaway roots, wired into the app under test."""
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    file_layer = Workspace(
        workspaces_root=workspaces_root,
        skills_root=skills_root,
        read_limit_chars=50_000,
        diff_file_limit_bytes=1_000_000,
        diff_total_limit_bytes=10_000_000,
    )
    app.state.workspace = file_layer
    return file_layer
