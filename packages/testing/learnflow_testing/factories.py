"""factory_boy factories for backend models (async SQLAlchemy).

Factories build persisted rows against an injected async session. Bind the
test's transactional session with :func:`bind_session` before use (the conftest
fixture does this), then ``await UserFactory.create(...)``.

**Precondition: an active ``db_session``.** A factory used without a bound
session (no ``db_session`` fixture in scope, or a stale class-level binding left
by an earlier test) fails fast with a clear ``RuntimeError`` instead of an opaque
crash deep inside SQLAlchemy. Depend on ``db_session`` (which calls
:func:`bind_session`) in any test that creates rows.
"""

from __future__ import annotations

from typing import Any

import factory
from app.models.project import Project
from app.models.user import User
from async_factory_boy.factory.sqlalchemy import AsyncSQLAlchemyFactory
from sqlalchemy.ext.asyncio import AsyncSession


class _SessionBoundFactory(AsyncSQLAlchemyFactory):
    """Base factory that fails loudly when no async session is bound.

    ``async-factory-boy`` reads ``cls._meta.sqlalchemy_session`` and dereferences
    it without checking — an unset (``None``) session surfaces as an obscure
    ``AttributeError`` mid-build. We intercept at the ``create`` entry point and
    raise a clear ``RuntimeError`` naming the missing precondition instead.
    """

    class Meta:
        abstract = True

    @classmethod
    async def create(cls, **kwargs: Any) -> Any:
        if cls._meta.sqlalchemy_session is None:
            raise RuntimeError(
                f"{cls.__name__} requires an active db_session fixture: no "
                "sqlalchemy_session is bound. Depend on the db_session fixture "
                "(which calls bind_session) before using factories."
            )
        return await super().create(**kwargs)


class UserFactory(_SessionBoundFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "flush"

    # ``name`` is UNIQUE — Sequence keeps rows distinct across one test.
    name = factory.Sequence(lambda n: f"user-{n}")
    password_hash = "argon2-placeholder-hash"


class ProjectFactory(_SessionBoundFactory):
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
