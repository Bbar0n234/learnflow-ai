"""Password login against an account that has no password.

Making ``users.password_hash`` nullable created a shape the password flow never
had to handle: a user created through a provider. The rule is that such an
attempt is answered exactly like a wrong password — same status, same body — so
that the form cannot be used to find out how a given account signs in. A
distinguishable answer here would turn the login form into an account-type
oracle; a crash would turn it into a 500.

New file rather than an addition to ``test_login.py``: this scope belongs to the
OAuth iteration, and the existing password suites are left untouched.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from learnflow_testing.factories import UserFactory
from sqlalchemy.ext.asyncio import AsyncSession

from tests.auth._helpers import DEFAULT_PASSWORD, login, register

OAUTH_USER_NAME = "oauth-only-user"


@pytest.mark.integration
async def test_login_without_a_stored_password_is_rejected(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    await UserFactory.create(name=OAUTH_USER_NAME, password_hash=None)

    response = await login(auth_client, name=OAUTH_USER_NAME)

    assert response.status_code == 401


@pytest.mark.integration
async def test_login_without_a_stored_password_looks_like_a_wrong_password(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Byte-for-byte the same answer as an ordinary bad-credentials attempt, so
    # the form does not disclose that this account signs in with a provider.
    await UserFactory.create(name=OAUTH_USER_NAME, password_hash=None)
    await register(auth_client, name="password-user")

    oauth_attempt = await login(auth_client, name=OAUTH_USER_NAME)
    wrong_password = await login(
        auth_client, name="password-user", password=f"not-{DEFAULT_PASSWORD}"
    )

    assert oauth_attempt.status_code == wrong_password.status_code
    assert oauth_attempt.json() == wrong_password.json()


@pytest.mark.integration
async def test_login_for_an_unknown_name_looks_the_same_too(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    # The third arm of the same rule: existence, password-lessness and a wrong
    # password are indistinguishable from outside.
    await UserFactory.create(name=OAUTH_USER_NAME, password_hash=None)

    oauth_attempt = await login(auth_client, name=OAUTH_USER_NAME)
    unknown = await login(auth_client, name="nobody-here")

    assert oauth_attempt.json() == unknown.json()
