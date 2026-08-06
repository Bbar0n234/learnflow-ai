"""Small builders shared by the handler tests in this scope."""

from __future__ import annotations

from app.models.project import Project
from app.models.user import User
from learnflow_testing.factories import ProjectFactory, UserFactory


async def create_owned_project(user: User, **kwargs: object) -> Project:
    """A project owned by the given (authenticated) user."""
    project: Project = await ProjectFactory.create(user=user, **kwargs)
    return project


async def create_other_project(**kwargs: object) -> Project:
    """A project owned by some *other* user — for ownership-404 assertions."""
    other = await UserFactory.create()
    project: Project = await ProjectFactory.create(user=other, **kwargs)
    return project
