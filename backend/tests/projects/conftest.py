"""Local fixtures for the Projects & artifacts scope (S4).

Adds two factories the shared ``learnflow_testing`` package does not ship —
``ArtifactFactory`` and ``ThreadViewFactory`` — modelled on the shared ones
(async-factory-boy, bound to the test's transactional session). They are bound
per test by an autouse fixture that piggybacks on ``db_session`` (which the
backend conftest already wires for the shared factories).
"""

from __future__ import annotations

import pytest
from app.models.artifact import Artifact
from app.models.thread_view import ThreadView
from async_factory_boy.factory.sqlalchemy import AsyncSQLAlchemyFactory

# Import from the defining submodule: factory/__init__ re-exports these without
# listing them in __all__, which trips mypy's no_implicit_reexport on
# ``factory.Sequence`` / ``factory.SubFactory``.
from factory.declarations import Sequence, SubFactory
from learnflow_testing.factories import ProjectFactory, bind_session
from sqlalchemy.ext.asyncio import AsyncSession


class ThreadViewFactory(AsyncSQLAlchemyFactory):
    class Meta:
        model = ThreadView
        sqlalchemy_session_persistence = "flush"

    title = Sequence(lambda n: f"thread-{n}")
    project = SubFactory(ProjectFactory)


class ArtifactFactory(AsyncSQLAlchemyFactory):
    class Meta:
        model = Artifact
        sqlalchemy_session_persistence = "flush"

    title = Sequence(lambda n: f"artifact-{n}")
    type = "summary"
    content = "# Body\n\nArtifact content."
    project = SubFactory(ProjectFactory)


@pytest.fixture(autouse=True)
def _bind_local_factories(db_session: AsyncSession) -> None:
    """Point the scope-local factories at the active transactional session."""
    bind_session(db_session, ThreadViewFactory, ArtifactFactory)
