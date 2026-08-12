"""``OAuthService.login_with_provider`` against real PostgreSQL.

Find-or-create is where OAuth stops and the ordinary session machinery begins,
and it is written to lean on database constraints rather than on a look-before-
you-leap check — which is only testable against a real database, so this suite
runs on the transactional session (and, for the concurrency case, on two
independent committed ones).

Two collisions are load-bearing and both are covered. A display name that is
already taken must be resolved by suffixing rather than by refusing the login,
because the user did not choose that name and cannot fix it. Two callbacks
racing for the same provider account — the double-tab case — must both end up
logged into the *same* user instead of one of them getting a 500.

Naming: every case here drives the one public entry point
(``login_with_provider``), so the names carry the condition and the expectation
in prose instead of repeating that unit — a deliberate deviation from
``test_<unit>_<condition>_<expected>``, applied consistently across the suite.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from app.infra.oauth.base import OAuthProfile
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.services.exceptions import OAuthAccountCreationError
from app.services.oauth import OAuthService
from learnflow_testing.factories import UserFactory
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from tests.oauth.conftest import build_settings


def _profile(
    account_id: str = "ya-1",
    *,
    provider: str = "yandex",
    email: str | None = "user@yandex.ru",
    display_name: str | None = "Иван",
) -> OAuthProfile:
    return OAuthProfile(
        provider=provider,
        provider_account_id=account_id,
        email=email,
        display_name=display_name,
    )


def _service(session: AsyncSession) -> OAuthService:
    return OAuthService(session, build_settings())


@pytest.mark.integration
async def test_first_login_creates_a_passwordless_user_and_a_link(
    db_session: AsyncSession,
) -> None:
    user, access, refresh, new_user = await _service(db_session).login_with_provider(
        _profile("ya-100", display_name="Иван Петров")
    )

    assert new_user is True
    assert access and refresh
    assert user.name == "Иван Петров"
    assert user.password_hash is None
    account = (
        await db_session.execute(
            select(OAuthAccount).where(OAuthAccount.provider_account_id == "ya-100")
        )
    ).scalar_one()
    assert account.user_id == user.id
    assert account.provider == "yandex"


@pytest.mark.integration
async def test_logging_in_again_reuses_the_same_user(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    first, _, _, _ = await service.login_with_provider(_profile("ya-101"))

    second, _, _, new_user = await service.login_with_provider(_profile("ya-101"))

    assert second.id == first.id
    assert new_user is False
    # Counted by this case's own name, not over the whole table: the race case
    # below really commits rows, and a run killed before its cleanup would
    # otherwise redden two tests that have nothing to do with the defect.
    users = await db_session.scalar(
        select(func.count()).select_from(User).where(User.name.like("Иван%"))
    )
    assert users == 1


@pytest.mark.integration
async def test_each_login_refreshes_the_stored_email(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    await service.login_with_provider(_profile("ya-102", email="old@yandex.ru"))

    await service.login_with_provider(_profile("ya-102", email="new@yandex.ru"))

    account = (
        await db_session.execute(
            select(OAuthAccount).where(OAuthAccount.provider_account_id == "ya-102")
        )
    ).scalar_one()
    assert account.email == "new@yandex.ru"


@pytest.mark.integration
async def test_an_email_withdrawn_by_the_provider_is_cleared(
    db_session: AsyncSession,
) -> None:
    # The column records what the provider says *now* (a revoked scope, an
    # address removed upstream), not the best value ever seen.
    service = _service(db_session)
    await service.login_with_provider(_profile("ya-103", email="was@yandex.ru"))

    await service.login_with_provider(_profile("ya-103", email=None))

    account = (
        await db_session.execute(
            select(OAuthAccount).where(OAuthAccount.provider_account_id == "ya-103")
        )
    ).scalar_one()
    assert account.email is None


@pytest.mark.integration
async def test_the_same_person_on_two_providers_stays_two_accounts(
    db_session: AsyncSession,
) -> None:
    # Auto-linking by email is deliberately out of scope: identity is the
    # (provider, account id) pair and nothing else.
    service = _service(db_session)
    first, _, _, _ = await service.login_with_provider(
        _profile("same-id", provider="yandex", email="one@example.com")
    )

    second, _, _, new_user = await service.login_with_provider(
        _profile("same-id", provider="google", email="one@example.com")
    )

    assert second.id != first.id
    assert new_user is True


@pytest.mark.integration
async def test_a_taken_display_name_is_resolved_with_a_suffix(
    db_session: AsyncSession,
) -> None:
    await UserFactory.create(name="Иван")

    user, _, _, new_user = await _service(db_session).login_with_provider(
        _profile("ya-104", display_name="Иван")
    )

    assert new_user is True
    assert user.name != "Иван"
    assert user.name.startswith("Иван_")
    users = await db_session.scalar(
        select(func.count()).select_from(User).where(User.name.like("Иван%"))
    )
    assert users == 2  # the pre-existing account was not touched


@pytest.mark.integration
async def test_a_profile_without_a_display_name_still_gets_a_user(
    db_session: AsyncSession,
) -> None:
    user, _, _, _ = await _service(db_session).login_with_provider(
        _profile("ya-105", display_name=None)
    )

    assert user.name.startswith("yandex_")


@pytest.mark.integration
@pytest.mark.parametrize("display_name", ["   ", "\t\n", ""])
async def test_a_blank_display_name_is_treated_as_missing(
    db_session: AsyncSession, display_name: str
) -> None:
    user, _, _, _ = await _service(db_session).login_with_provider(
        _profile("ya-106", display_name=display_name)
    )

    assert user.name.startswith("yandex_")


@pytest.mark.integration
async def test_an_exhausted_name_search_fails_the_login_instead_of_looping(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # With the random suffix pinned, every candidate collides; the retry budget
    # must end in a domain error the route can map, not an endless loop or a
    # raw IntegrityError surfacing as a 500.
    #
    # Pinning the suffix reaches past the public surface into the primitive the
    # implementation happens to use, which is a known cost: swapping token_hex
    # for token_urlsafe or uuid4().hex would redden this case (and the two
    # staged the same way in test_callback.py / test_siem_events.py) without
    # any behaviour changing. It is accepted deliberately — the service has no
    # injectable suffix generator, and the only public route to "the name
    # budget is exhausted" would be occupying all 65 536 suffixes of a name.
    # Adding that seam is a production decision, not a test one; if it ever
    # lands, these three cases move onto it.
    monkeypatch.setattr("app.services.oauth.secrets.token_hex", lambda _: "beef")
    await UserFactory.create(name="Тёзка")
    await UserFactory.create(name="Тёзка_beef")

    with pytest.raises(OAuthAccountCreationError):
        await _service(db_session).login_with_provider(
            _profile("ya-107", display_name="Тёзка")
        )


@pytest.mark.integration
async def test_a_long_display_name_is_trimmed_to_fit_the_column(
    db_session: AsyncSession,
) -> None:
    user, _, _, _ = await _service(db_session).login_with_provider(
        _profile("ya-108", display_name="и" * 300)
    )

    assert len(user.name) <= 100


# ---------------------------------------------------------------------------
# The double-callback race — two committed sessions, not one
# ---------------------------------------------------------------------------


@pytest.fixture
def committed_sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session maker for work that must really commit.

    The shared ``db_session`` cannot express a race: everything it does lives
    in a single transaction, so a second actor could never be invisible to the
    first. Rows created through this maker are committed for real, so the test
    that uses it cleans up after itself.
    """
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.integration
async def test_two_callbacks_racing_for_one_account_land_on_the_same_user(
    committed_sessions: async_sessionmaker[AsyncSession],
) -> None:
    # Both flows look up the link, both miss, both insert. The unique index
    # lets exactly one through; the loser must degrade to a login rather than
    # surface an IntegrityError as a 500, and no duplicate user may remain.
    account_id = f"race-{uuid.uuid4().hex}"
    settings = build_settings()

    async def _login(display_name: str) -> uuid.UUID:
        async with committed_sessions() as session, session.begin():
            user, _, _, _ = await OAuthService(session, settings).login_with_provider(
                _profile(account_id, display_name=display_name)
            )
            return user.id

    try:
        first_id, second_id = await asyncio.gather(
            _login("Гонщик Первый"), _login("Гонщик Второй")
        )

        assert first_id == second_id
        async with committed_sessions() as check:
            links = await check.scalar(
                select(func.count())
                .select_from(OAuthAccount)
                .where(OAuthAccount.provider_account_id == account_id)
            )
        assert links == 1
    finally:
        async with committed_sessions() as cleanup, cleanup.begin():
            owners = select(OAuthAccount.user_id).where(
                OAuthAccount.provider_account_id == account_id
            )
            await cleanup.execute(delete(User).where(User.id.in_(owners)))


@pytest.mark.integration
async def test_a_link_created_elsewhere_is_found_rather_than_duplicated(
    db_session: AsyncSession,
) -> None:
    # The lookup-then-login path, reached through the public entry point: a
    # link that already exists must produce a session for its owner.
    owner: User = await UserFactory.create(name="Хозяин связки")
    db_session.add(
        OAuthAccount(
            user_id=owner.id,
            provider="github",
            provider_account_id="gh-777",
            email="owner@github.com",
        )
    )
    await db_session.flush()

    user, _, _, new_user = await _service(db_session).login_with_provider(
        _profile("gh-777", provider="github", display_name="Кто-то другой")
    )

    assert user.id == owner.id
    assert new_user is False
    assert user.name == "Хозяин связки"  # a login never renames its user
