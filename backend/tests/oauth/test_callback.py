"""``GET /api/auth/oauth/{provider}/callback`` — the return leg of the flow.

The callback is the only endpoint an attacker can address directly, so its
contract is an *ordered* one: provider validity, then the budget, then the
user's refusal, then the signed cookie and state, then geo, then the exchange,
then find-or-create. Each test drives one branch and pins two things about it —
where the browser is sent (a code from the closed ``/login?error=`` registry)
and what happens to the ``oauth_flow`` cookie, which every terminal branch must
extinguish and the two non-terminal ones (404, 429) must leave alone.

Ordering is asserted by making an *earlier* branch fire while a later one would
also have matched — e.g. a request that is both rate-limited and carrying a
refusal, or a refusal carrying a tampered cookie. The success path runs all the
way into PostgreSQL and out through the real refresh endpoint, which is how the
"access token never travels in a URL" rule is checked: the SPA can only get one
by spending the cookie.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.infra.oauth.base import OAuthProfile
from app.infra.oauth.exceptions import OAuthProviderError
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.oauth._helpers import (
    FakeProvider,
    cookie_header,
    cookie_value,
    geoip_reader_for,
    is_deleted_cookie,
    make_flow_cookie,
)
from tests.oauth.conftest import OAuthStand, StandFactory

FLOW_COOKIE = "oauth_flow"
REFRESH_COOKIE = "refresh_token"
STATE = "state-under-test"
VERIFIER = "verifier-under-test"


def _callback_url(provider: str) -> str:
    return f"/api/auth/oauth/{provider}/callback"


def _flow_cookie(**overrides: Any) -> dict[str, str]:
    """The cookie a browser carries back from a flow started for ``yandex``."""
    params: dict[str, Any] = {
        "state": STATE,
        "verifier": VERIFIER,
        "provider": "yandex",
        "next_path": "/",
    }
    params.update(overrides)
    return {FLOW_COOKIE: make_flow_cookie(**params)}


async def _callback(
    stand: OAuthStand,
    *,
    provider: str = "yandex",
    cookies: dict[str, str] | None = None,
    **query: str,
) -> Response:
    return await stand.client.get(
        _callback_url(provider), params=query, cookies=cookies
    )


# ---------------------------------------------------------------------------
# Gate 1: the provider must exist — before anything else is even parsed
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_unknown_provider_is_a_404(stand: OAuthStand) -> None:
    response = await stand.client.get(_callback_url("nosuch"))

    assert response.status_code == 404


@pytest.mark.integration
async def test_callback_unknown_provider_is_a_404_even_on_an_error_query(
    stand: OAuthStand,
) -> None:
    # Reaching an endpoint that does not exist must not be answered with the
    # friendly /login redirect meant for real flows.
    response = await stand.client.get(
        _callback_url("nosuch"), params={"error": "access_denied"}
    )

    assert response.status_code == 404
    assert "location" not in response.headers


@pytest.mark.integration
async def test_callback_404_leaves_a_running_flow_untouched(stand: OAuthStand) -> None:
    response = await stand.client.get(_callback_url("nosuch"), cookies=_flow_cookie())

    assert response.status_code == 404
    assert cookie_header(response, FLOW_COOKIE) is None


# ---------------------------------------------------------------------------
# Gate 2: the callback's own per-IP budget
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_eleventh_within_the_window_is_rejected(
    stand: OAuthStand,
) -> None:
    for _ in range(10):
        await _callback(stand, error="access_denied")

    response = await _callback(stand, error="access_denied")

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.integration
async def test_callback_rate_limited_leaves_the_flow_cookie_alone(
    stand: OAuthStand,
) -> None:
    # Non-terminal branch: one extra request must not be able to kill a login
    # that is legitimately in progress.
    for _ in range(10):
        await _callback(stand, error="access_denied")

    response = await stand.client.get(
        _callback_url("yandex"), cookies=_flow_cookie(), params={"state": STATE}
    )

    assert response.status_code == 429
    assert cookie_header(response, FLOW_COOKIE) is None


@pytest.mark.integration
async def test_callback_spends_a_budget_separate_from_authorize(
    stand: OAuthStand,
) -> None:
    # One login costs one of each; a shared key would halve the real budget.
    for _ in range(10):
        await stand.client.get("/api/auth/oauth/yandex/authorize")

    response = await _callback(stand, error="access_denied")

    assert response.status_code == 302


@pytest.mark.integration
async def test_callback_budget_is_counted_per_client_address(
    stand_factory: StandFactory,
) -> None:
    # Same measurement as on authorize: the budget is per IP, and a single
    # shared bucket would let one caller shut the return leg for everyone.
    stand = await stand_factory(client_ip_source="x-real-ip")
    heavy = {"X-Real-IP": "203.0.113.10"}
    fresh = {"X-Real-IP": "198.51.100.7"}
    url = _callback_url("yandex")

    for _ in range(10):
        await stand.client.get(url, params={"error": "access_denied"}, headers=heavy)
    exhausted = await stand.client.get(
        url, params={"error": "access_denied"}, headers=heavy
    )
    other_client = await stand.client.get(
        url, params={"error": "access_denied"}, headers=fresh
    )

    assert exhausted.status_code == 429
    assert other_client.status_code == 302


# ---------------------------------------------------------------------------
# Branch 1: the user refused on the provider's screen
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_user_refusal_returns_to_login_as_access_denied(
    stand: OAuthStand,
) -> None:
    response = await _callback(stand, error="access_denied")

    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=access_denied"


@pytest.mark.integration
async def test_callback_user_refusal_is_read_before_the_state(
    stand: OAuthStand,
) -> None:
    # The cookie is deliberately unusable (wrong secret) and no state is sent:
    # if the order were reversed this would come back as flow_expired.
    response = await stand.client.get(
        _callback_url("yandex"),
        params={"error": "access_denied"},
        cookies={FLOW_COOKIE: make_flow_cookie(jwt_secret="another-secret")},
    )

    assert response.headers["location"] == "/login?error=access_denied"


@pytest.mark.integration
async def test_callback_user_refusal_extinguishes_the_cookie_it_got(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(
        _callback_url("yandex"),
        params={"error": "access_denied"},
        cookies=_flow_cookie(),
    )

    assert is_deleted_cookie(response, FLOW_COOKIE)


@pytest.mark.integration
async def test_callback_user_refusal_without_a_cookie_sets_none(
    stand: OAuthStand,
) -> None:
    # Nothing to delete: emitting a Set-Cookie here would be noise on a
    # response that never owned a flow.
    response = await _callback(stand, error="access_denied")

    assert cookie_header(response, FLOW_COOKIE) is None


# ---------------------------------------------------------------------------
# Branch 2: the signed cookie and the state must agree
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_without_a_cookie_is_an_expired_flow(
    stand: OAuthStand,
) -> None:
    response = await _callback(stand, state=STATE, code="auth-code")

    assert response.headers["location"] == "/login?error=flow_expired"
    assert cookie_header(response, FLOW_COOKIE) is None


@pytest.mark.integration
@pytest.mark.parametrize(
    ("cookies", "query", "why"),
    [
        (_flow_cookie(expires_in=-1), {"state": STATE}, "expired"),
        (
            {FLOW_COOKIE: make_flow_cookie(jwt_secret="forged")},
            {"state": "state-123"},
            "forged signature",
        ),
        (_flow_cookie(), {"state": "not-the-state"}, "state mismatch"),
        (_flow_cookie(), {}, "no state at all"),
        ({FLOW_COOKIE: "garbage"}, {"state": STATE}, "unparsable cookie"),
    ],
)
async def test_callback_every_broken_flow_collapses_into_one_branch(
    stand: OAuthStand,
    cookies: dict[str, str],
    query: dict[str, str],
    why: str,
) -> None:
    response = await stand.client.get(
        _callback_url("yandex"), params=query, cookies=cookies
    )

    assert response.headers["location"] == "/login?error=flow_expired", why
    assert is_deleted_cookie(response, FLOW_COOKIE), why


@pytest.mark.integration
async def test_callback_rejects_a_cookie_from_another_provider(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(fallback_country="US")

    response = await stand.client.get(
        _callback_url("google"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(provider="yandex"),
    )

    assert response.headers["location"] == "/login?error=flow_expired"
    assert stand.providers["google"].exchange_calls == []


@pytest.mark.integration
async def test_callback_replay_lands_on_the_expired_flow_branch(
    stand: OAuthStand,
) -> None:
    # The second visit arrives without the cookie, because the first visit
    # extinguished it — the parallel-tab case described in the brief.
    first = await stand.client.get(
        _callback_url("yandex"),
        params={"error": "access_denied"},
        cookies=_flow_cookie(),
    )
    assert is_deleted_cookie(first, FLOW_COOKIE)

    replay = await _callback(stand, state=STATE, code="auth-code")

    assert replay.headers["location"] == "/login?error=flow_expired"


# ---------------------------------------------------------------------------
# Branch 3: geo, re-checked on the way back
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_geo_is_rechecked_on_the_return_leg(stand: OAuthStand) -> None:
    # A flow may have started outside Russia and come back from a Russian
    # address — or address the callback directly, bypassing the UI entirely.
    response = await stand.client.get(
        _callback_url("google"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(provider="google"),
    )

    assert response.headers["location"] == (
        "/login?error=provider_not_available_in_region"
    )
    assert is_deleted_cookie(response, FLOW_COOKIE)
    assert stand.providers["google"].exchange_calls == []


@pytest.mark.integration
async def test_callback_geo_is_checked_after_the_state_not_before(
    stand: OAuthStand,
) -> None:
    # A blocked provider with a broken cookie must still read as flow_expired:
    # the geo answer would otherwise tell an unauthenticated caller which
    # providers exist for which regions.
    response = await stand.client.get(
        _callback_url("google"),
        params={"state": "wrong"},
        cookies=_flow_cookie(provider="google"),
    )

    assert response.headers["location"] == "/login?error=flow_expired"


@pytest.mark.integration
async def test_callback_geo_follows_the_database_lookup_not_the_fallback(
    stand_factory: StandFactory,
) -> None:
    # The re-check on the return leg has to run the same resolver as the rest:
    # reading the configured fallback directly would stay green here while the
    # "IP changed between the steps" scenario stopped being checked at all.
    stand = await stand_factory(
        fallback_country="US", geoip_reader=geoip_reader_for({"country_code": "RU"})
    )

    response = await stand.client.get(
        _callback_url("google"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(provider="google"),
    )

    assert response.headers["location"] == (
        "/login?error=provider_not_available_in_region"
    )
    assert is_deleted_cookie(response, FLOW_COOKIE)
    assert stand.providers["google"].exchange_calls == []


@pytest.mark.integration
async def test_callback_geo_lookup_can_also_lift_a_restrictive_fallback(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(
        fallback_country="RU", geoip_reader=geoip_reader_for({"country_code": "US"})
    )

    response = await stand.client.get(
        _callback_url("google"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(provider="google"),
    )

    assert response.headers["location"] == "/"
    assert stand.providers["google"].exchange_calls != []


# ---------------------------------------------------------------------------
# Branch 4: the exchange with the provider
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_provider_failure_returns_as_unavailable(
    stand: OAuthStand,
) -> None:
    stand.yandex.exchange_error = OAuthProviderError("yandex", "token exchange failed")

    response = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    assert response.headers["location"] == "/login?error=provider_unavailable"
    assert is_deleted_cookie(response, FLOW_COOKIE)


@pytest.mark.integration
async def test_callback_broken_profile_call_is_also_unavailable(
    stand: OAuthStand,
) -> None:
    stand.yandex.profile_error = OAuthProviderError("yandex", "profile fetch failed")

    response = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    assert response.headers["location"] == "/login?error=provider_unavailable"


@pytest.mark.integration
async def test_callback_without_a_code_never_calls_the_provider(
    stand: OAuthStand,
) -> None:
    # Direct navigation to the callback, past the provider: the exchange has
    # nothing to exchange.
    response = await stand.client.get(
        _callback_url("yandex"), params={"state": STATE}, cookies=_flow_cookie()
    )

    assert response.headers["location"] == "/login?error=provider_unavailable"
    assert stand.yandex.exchange_calls == []


@pytest.mark.integration
async def test_callback_exchange_replays_the_verifier_and_redirect_uri(
    stand: OAuthStand,
) -> None:
    # PKCE only proves anything if the verifier that comes out of the cookie is
    # the one that goes to the provider; the redirect_uri must match the one
    # sent at authorize, or the provider rejects the exchange.
    await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    call = stand.yandex.exchange_calls[-1]
    assert call.code == "auth-code"
    assert call.verifier == VERIFIER
    assert call.redirect_uri == ("http://localhost:5173/api/auth/oauth/yandex/callback")


# ---------------------------------------------------------------------------
# Branch 6: success
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_success_returns_the_user_to_the_remembered_path(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(next_path="/projects/p1/artifacts"),
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/projects/p1/artifacts"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("stored", "location"),
    [
        ("/\\evil.example", "/%5Cevil.example"),
        ("/\\/evil.example", "/%5C/evil.example"),
    ],
    ids=["backslash", "backslash-slash"],
)
async def test_callback_a_backslash_in_next_cannot_leave_the_origin(
    stand: OAuthStand, stored: str, location: str
) -> None:
    # is_safe_next_path only rejects "//", so a backslash form survives into
    # the signed claim (pinned in test_flow_state.py). What actually keeps the
    # rule "no open redirects" is the emitted header: the backslash is quoted
    # before a browser can read it as an authority, so this asserts the header
    # rather than the claim — if either layer changes, this case is the one
    # that has to be re-argued.
    response = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(next_path=stored),
    )

    assert response.status_code == 302
    assert response.headers["location"] == location
    assert not response.headers["location"].startswith("//")


@pytest.mark.integration
async def test_callback_success_sets_refresh_and_clears_the_flow_cookie(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    assert cookie_value(response, REFRESH_COOKIE)
    assert is_deleted_cookie(response, FLOW_COOKIE)


@pytest.mark.integration
async def test_callback_no_access_token_travels_through_the_redirect(
    stand: OAuthStand,
) -> None:
    # The redirect URL is a dirty channel (history, logs, Referer). The SPA is
    # expected to spend the refresh cookie instead — which is exactly what this
    # test does, proving the token is reachable without ever being in the URL.
    callback = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(next_path="/projects/p1"),
    )
    assert callback.headers["location"] == "/projects/p1"  # no query, no fragment

    refresh = await stand.client.post("/api/auth/refresh")

    assert refresh.status_code == 200
    assert refresh.json()["access_token"]


@pytest.mark.integration
async def test_callback_first_login_creates_the_user_and_the_link(
    stand: OAuthStand, db_session: AsyncSession
) -> None:
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-9001",
        email="new@yandex.ru",
        display_name="Новичок",
    )

    await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    account = (
        await db_session.execute(
            select(OAuthAccount).where(OAuthAccount.provider_account_id == "ya-9001")
        )
    ).scalar_one()
    user = await db_session.get(User, account.user_id)
    assert user is not None
    assert user.name == "Новичок"
    assert user.password_hash is None  # an OAuth account has no password
    assert account.email == "new@yandex.ru"


@pytest.mark.integration
async def test_callback_logging_in_twice_creates_no_second_user(
    stand: OAuthStand, db_session: AsyncSession
) -> None:
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-9002",
        email="repeat@yandex.ru",
        display_name="Повторный",
    )

    for _ in range(2):
        await stand.client.get(
            _callback_url("yandex"),
            params={"state": STATE, "code": "auth-code"},
            cookies=_flow_cookie(),
        )

    linked = await db_session.scalar(
        select(func.count())
        .select_from(OAuthAccount)
        .where(OAuthAccount.provider_account_id == "ya-9002")
    )
    named = await db_session.scalar(
        select(func.count()).select_from(User).where(User.name == "Повторный")
    )
    assert linked == 1
    assert named == 1


@pytest.mark.integration
async def test_callback_profile_without_an_email_still_creates_the_link(
    stand_factory: StandFactory, db_session: AsyncSession
) -> None:
    # Email is optional across the abstraction (GitHub can withhold it), so a
    # profile without one must still produce a usable account.
    stand = await stand_factory(
        providers={"yandex": FakeProvider("yandex")}, fallback_country="RU"
    )
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-9003",
        email=None,
        display_name="Ровно тот",
    )

    await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    account = (
        await db_session.execute(
            select(OAuthAccount).where(OAuthAccount.provider_account_id == "ya-9003")
        )
    ).scalar_one()
    assert account.provider == "yandex"
    assert account.email is None


# ---------------------------------------------------------------------------
# Branch 5: find-or-create could not settle on a user
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_callback_failed_find_or_create_returns_the_generic_code(
    stand: OAuthStand, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every name candidate is made to collide: the display name is taken, and
    # the random suffix is pinned so the retries land on a taken name too. The
    # service exhausts its budget and the route must answer with the registry's
    # generic code rather than a 500. Pinning the suffix reaches into the
    # implementation's own primitive — the accepted trade-off is argued once,
    # in test_oauth_service.py next to the same staging.
    monkeypatch.setattr("app.services.oauth.secrets.token_hex", lambda _: "beef")
    db_session.add_all(
        [
            User(name="Занятое Имя", password_hash="x"),
            User(name="Занятое Имя_beef", password_hash="x"),
        ]
    )
    await db_session.flush()
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-9100",
        email=None,
        display_name="Занятое Имя",
    )

    response = await stand.client.get(
        _callback_url("yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/login?error=oauth_failed"
    assert is_deleted_cookie(response, FLOW_COOKIE)
