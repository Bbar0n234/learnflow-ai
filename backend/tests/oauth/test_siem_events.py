"""What the OAuth endpoints report to SIEM — and, just as firmly, what they don't.

The event vocabulary is a closed contract shared with the siem-service, and the
brief maps the callback's branches onto it deliberately: a broken or forged flow
is a possible CSRF signal and a failed find-or-create is a real malfunction, so
both are reported; a user who changed their mind, a provider that is down, and a
provider that is simply not offered in this region are not security events at
all. Reporting the quiet branches would drown the loud ones, so the negative
cases here carry as much weight as the positive ones.

Events are read with ``structlog.testing.capture_logs``, which sees the keyword
payload before any renderer touches it.

Naming: the unit under test here is the emission itself rather than one
function, so case names read as prose ("what is reported, when") instead of
the ``test_<unit>_<condition>_<expected>`` shape — a deliberate deviation,
applied consistently across this suite.
"""

from __future__ import annotations

import pytest
from app.infra.oauth.base import OAuthProfile
from app.infra.oauth.exceptions import OAuthProviderError
from app.models.user import User
from siem_contracts import (
    AUTH_OAUTH_FAILED,
    AUTH_OAUTH_SUCCESS,
    RATE_LIMIT_OAUTH_EXCEEDED,
)
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from tests.oauth._helpers import event_types, make_flow_cookie, security_events
from tests.oauth.conftest import OAuthStand, StandFactory

FLOW_COOKIE = "oauth_flow"
STATE = "state-under-test"
CALLBACK = "/api/auth/oauth/{provider}/callback"
AUTHORIZE = "/api/auth/oauth/{provider}/authorize"


def _flow_cookie(provider: str = "yandex", state: str = STATE) -> dict[str, str]:
    return {
        FLOW_COOKIE: make_flow_cookie(
            state=state, verifier="verifier-1", provider=provider, next_path="/"
        )
    }


@pytest.mark.integration
async def test_successful_login_is_reported_with_the_provider_and_novelty(
    stand: OAuthStand,
) -> None:
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-siem-1",
        email="siem@yandex.ru",
        display_name="Первый Вход",
    )

    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"),
            params={"state": STATE, "code": "auth-code"},
            cookies=_flow_cookie(),
        )

    events = security_events(logs)
    assert [entry["event_type"] for entry in events] == [AUTH_OAUTH_SUCCESS]
    assert events[0]["metadata"] == {"provider": "yandex", "new_user": True}


@pytest.mark.integration
async def test_a_returning_user_is_reported_as_not_new(stand: OAuthStand) -> None:
    # The same event type carries the distinction — first login is a login with
    # a flag, not a separate "registration" type.
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-siem-2",
        email=None,
        display_name="Возвращенец",
    )
    await stand.client.get(
        CALLBACK.format(provider="yandex"),
        params={"state": STATE, "code": "auth-code"},
        cookies=_flow_cookie(),
    )

    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"),
            params={"state": STATE, "code": "auth-code"},
            cookies=_flow_cookie(),
        )

    events = security_events(logs)
    assert events[0]["metadata"] == {"provider": "yandex", "new_user": False}


@pytest.mark.integration
@pytest.mark.parametrize(
    ("cookies", "query"),
    [
        ({}, {"state": STATE, "code": "auth-code"}),
        (_flow_cookie(), {"state": "mismatched", "code": "auth-code"}),
    ],
    ids=["no-cookie", "state-mismatch"],
)
async def test_a_broken_flow_is_reported_as_a_failed_login(
    stand: OAuthStand, cookies: dict[str, str], query: dict[str, str]
) -> None:
    # State that does not line up is the CSRF-shaped branch — the one worth
    # alerting on.
    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"), params=query, cookies=cookies
        )

    events = security_events(logs)
    assert [entry["event_type"] for entry in events] == [AUTH_OAUTH_FAILED]
    assert events[0]["metadata"]["provider"] == "yandex"
    assert events[0]["metadata"]["reason"] == "flow_expired"


@pytest.mark.integration
async def test_an_unsettled_find_or_create_is_reported_as_a_failed_login(
    stand: OAuthStand, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Staged the same way as in test_callback.py: the display name is taken and
    # the random suffix is pinned, so every retry lands on a taken name too
    # (the cost of pinning the primitive is argued in test_oauth_service.py).
    monkeypatch.setattr("app.services.oauth.secrets.token_hex", lambda _: "beef")
    db_session.add_all(
        [
            User(name="Тёзка", password_hash="x"),
            User(name="Тёзка_beef", password_hash="x"),
        ]
    )
    await db_session.flush()
    stand.yandex.profile = OAuthProfile(
        provider="yandex",
        provider_account_id="ya-siem-3",
        email=None,
        display_name="Тёзка",
    )

    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"),
            params={"state": STATE, "code": "auth-code"},
            cookies=_flow_cookie(),
        )

    events = security_events(logs)
    assert event_types(logs) == [AUTH_OAUTH_FAILED]
    assert events[0]["metadata"]["reason"] == "oauth_failed"


@pytest.mark.integration
async def test_a_user_who_changed_their_mind_is_not_a_security_event(
    stand: OAuthStand,
) -> None:
    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"),
            params={"error": "access_denied"},
            cookies=_flow_cookie(),
        )

    assert security_events(logs) == []


@pytest.mark.integration
async def test_a_provider_error_code_is_not_a_security_event(stand: OAuthStand) -> None:
    # A provider answering `error=server_error` (or a revoked client secret) is
    # the same outage category as a failed token exchange: it earns a warning
    # in the log, not an entry in the analyst's queue.
    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"),
            params={"error": "server_error"},
            cookies=_flow_cookie(),
        )

    assert security_events(logs) == []


@pytest.mark.integration
async def test_a_region_refusal_is_not_a_security_event(stand: OAuthStand) -> None:
    # Showing fewer buttons in a region is policy, not an incident; it would
    # otherwise fire on every ordinary Russian visitor.
    with capture_logs() as logs:
        await stand.client.get(AUTHORIZE.format(provider="google"))

    assert security_events(logs) == []


@pytest.mark.integration
async def test_a_region_refusal_on_the_callback_is_not_a_security_event(
    stand: OAuthStand,
) -> None:
    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="google"),
            params={"state": STATE, "code": "auth-code"},
            cookies=_flow_cookie(provider="google"),
        )

    assert security_events(logs) == []


@pytest.mark.integration
async def test_an_unavailable_provider_is_not_a_security_event(
    stand: OAuthStand,
) -> None:
    # Someone else's outage is an operational signal, not an attack; it is
    # logged as a warning without the SIEM fields.
    stand.yandex.exchange_error = OAuthProviderError("yandex", "token exchange failed")

    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"),
            params={"state": STATE, "code": "auth-code"},
            cookies=_flow_cookie(),
        )

    assert security_events(logs) == []


@pytest.mark.integration
async def test_exceeding_the_authorize_budget_is_reported(stand: OAuthStand) -> None:
    for _ in range(10):
        await stand.client.get(AUTHORIZE.format(provider="yandex"))

    with capture_logs() as logs:
        await stand.client.get(AUTHORIZE.format(provider="yandex"))

    events = security_events(logs)
    assert [entry["event_type"] for entry in events] == [RATE_LIMIT_OAUTH_EXCEEDED]
    assert events[0]["metadata"]["key"].startswith("oauth_authorize:")


@pytest.mark.integration
async def test_exceeding_the_callback_budget_is_reported_under_its_own_key(
    stand: OAuthStand,
) -> None:
    for _ in range(10):
        await stand.client.get(
            CALLBACK.format(provider="yandex"), params={"error": "access_denied"}
        )

    with capture_logs() as logs:
        await stand.client.get(
            CALLBACK.format(provider="yandex"), params={"error": "access_denied"}
        )

    events = security_events(logs)
    assert [entry["event_type"] for entry in events] == [RATE_LIMIT_OAUTH_EXCEEDED]
    assert events[0]["metadata"]["key"].startswith("oauth_callback:")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("url", "params", "prefix"),
    [
        (AUTHORIZE, {}, "oauth_authorize"),
        (CALLBACK, {"error": "access_denied"}, "oauth_callback"),
    ],
    ids=["authorize", "callback"],
)
async def test_the_reported_key_names_the_client_that_spent_the_budget(
    stand_factory: StandFactory,
    url: str,
    params: dict[str, str],
    prefix: str,
) -> None:
    # The two cases above can only see the prefix, because every request under
    # ASGITransport comes from the same socket. Here the address is the test's
    # to choose, so the whole key is pinned — an analyst who cannot tell which
    # client tripped the limit has an event that says nothing.
    stand = await stand_factory(client_ip_source="x-real-ip")
    headers = {"X-Real-IP": "203.0.113.10"}
    endpoint = url.format(provider="yandex")

    for _ in range(10):
        await stand.client.get(endpoint, params=params, headers=headers)
    with capture_logs() as logs:
        await stand.client.get(endpoint, params=params, headers=headers)

    events = security_events(logs)
    assert [entry["event_type"] for entry in events] == [RATE_LIMIT_OAUTH_EXCEEDED]
    assert events[0]["metadata"]["key"] == f"{prefix}:203.0.113.10"


@pytest.mark.integration
async def test_listing_providers_reports_nothing(stand_factory: StandFactory) -> None:
    # A page load must not produce SIEM traffic.
    stand = await stand_factory(fallback_country="US")

    with capture_logs() as logs:
        await stand.client.get("/api/auth/providers")

    assert security_events(logs) == []
