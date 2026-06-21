"""factory_boy factories for backend models (async SQLAlchemy).

Factories build persisted rows against an injected async session. Bind the
test's transactional session with :func:`bind_session` before use (the conftest
fixture does this), then ``await UserFactory.create(...)``.
"""

from __future__ import annotations

from typing import Any

import factory
from app.models.project import Project
from app.models.user import User
from async_factory_boy.factory.sqlalchemy import AsyncSQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession


class UserFactory(AsyncSQLAlchemyFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "flush"

    # ``name`` is UNIQUE — Sequence keeps rows distinct across one test.
    name = factory.Sequence(lambda n: f"user-{n}")
    password_hash = "argon2-placeholder-hash"


class ProjectFactory(AsyncSQLAlchemyFactory):
    class Meta:
        model = Project
        sqlalchemy_session_persistence = "flush"

    name = factory.Sequence(lambda n: f"project-{n}")
    user = factory.SubFactory(UserFactory)


ALL_FACTORIES: tuple[type[AsyncSQLAlchemyFactory], ...] = (UserFactory, ProjectFactory)


def bind_session(session: AsyncSession, *factories: Any) -> None:
    """Point factories at the given async session.

    With no explicit factories, binds the project's default set. Call once per
    test (the ``db_session`` fixture wires this) so ``create`` persists into the
    test's transactional session.
    """
    targets = factories or ALL_FACTORIES
    for fct in targets:
        fct._meta.sqlalchemy_session = session
