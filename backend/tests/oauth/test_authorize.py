"""``GET /api/auth/oauth/{provider}/authorize`` — the outbound half of the flow.

The endpoint has to get four things right at once, and the suite takes them one
at a time: it must refuse a provider that is not configured before anything
else happens; it must spend a per-IP budget of its own; it must not let a
Russian client start a foreign provider's flow; and, on the happy path, it must
hand the provider a state and an S256 challenge that match what it just sealed
into the ``oauth_flow`` cookie — a mismatch there silently disables PKCE and the
CSRF check while everything still looks green in a browser.

The ``next`` parameter is checked from the open-redirect side: whatever a caller
puts in it, what ends up in the signed claim is a same-origin path.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.oauth._helpers import (
    JWT_SECRET,
    FakeProvider,
    cookie_attributes,
    cookie_header,
    cookie_value,
    flow_claims,
    geoip_reader_for,
    s256_challenge,
)
from tests.oauth.conftest import OAuthStand, StandFactory

FLOW_COOKIE = "oauth_flow"


def _authorize_url(provider: str) -> str:
    return f"/api/auth/oauth/{provider}/authorize"


async def _open_flow(
    stand: OAuthStand, provider: str = "yandex", **params: str
) -> dict[str, Any]:
    """Runs authorize and returns the decoded ``oauth_flow`` claims."""
    response = await stand.client.get(_authorize_url(provider), params=params)
    token = cookie_value(response, FLOW_COOKIE)
    assert token is not None
    return flow_claims(token, JWT_SECRET)


@pytest.mark.integration
@pytest.mark.parametrize("provider", ["nosuch", "vk", "yandex.ru"])
async def test_authorize_unknown_provider_is_a_404(
    stand: OAuthStand, provider: str
) -> None:
    response = await stand.client.get(_authorize_url(provider))

    assert response.status_code == 404


@pytest.mark.integration
async def test_authorize_inactive_provider_is_a_404_not_a_redirect(
    stand_factory: StandFactory,
) -> None:
    # "Known to the codebase" is not "active": a provider without credentials
    # is absent from the registry and must be rejected outright, never turned
    # into a friendly /login redirect.
    stand = await stand_factory(
        providers={"yandex": FakeProvider("yandex")}, fallback_country="US"
    )

    response = await stand.client.get(_authorize_url("google"))

    assert response.status_code == 404
    assert cookie_header(response, FLOW_COOKIE) is None


@pytest.mark.integration
async def test_authorize_redirects_the_browser_to_the_provider(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(_authorize_url("yandex"))

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://yandex.example/authorize")


@pytest.mark.integration
async def test_authorize_gives_the_provider_the_state_and_challenge_of_the_cookie(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(_authorize_url("yandex"))

    token = cookie_value(response, FLOW_COOKIE)
    assert token is not None
    claims = flow_claims(token, JWT_SECRET)
    call = stand.yandex.authorize_calls[-1]
    # The provider gets the state verbatim and the S256 hash of the verifier —
    # never the verifier itself, which is the entire point of PKCE.
    assert call.state == claims["state"]
    assert call.challenge == s256_challenge(claims["verifier"])
    assert call.challenge != claims["verifier"]


@pytest.mark.integration
async def test_authorize_each_flow_gets_a_fresh_state_and_verifier(
    stand: OAuthStand,
) -> None:
    first = await _open_flow(stand)
    second = await _open_flow(stand)

    assert first["state"] != second["state"]
    assert first["verifier"] != second["verifier"]


@pytest.mark.integration
async def test_authorize_redirect_uri_is_built_from_configuration_only(
    stand: OAuthStand,
) -> None:
    # A spoofed Host must not move the callback: the provider compares this
    # value against its registration, and the flow's cookies are host-scoped.
    await stand.client.get(
        _authorize_url("yandex"),
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
    )

    assert stand.yandex.authorize_calls[-1].redirect_uri == (
        "http://localhost:5173/api/auth/oauth/yandex/callback"
    )


@pytest.mark.integration
async def test_authorize_flow_cookie_is_scoped_and_hidden_from_js(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(_authorize_url("yandex"))

    raw = cookie_header(response, FLOW_COOKIE)
    assert raw is not None
    attrs = cookie_attributes(raw)
    assert attrs["path"] == "/api/auth/oauth"
    assert attrs["max-age"] == "600"
    assert attrs["samesite"].lower() == "lax"
    assert "httponly" in attrs


@pytest.mark.integration
async def test_authorize_flow_cookie_is_marked_secure_when_configured(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(secure_cookies=True)

    response = await stand.client.get(_authorize_url("yandex"))

    raw = cookie_header(response, FLOW_COOKIE)
    assert raw is not None
    assert "secure" in cookie_attributes(raw)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("requested", "stored"),
    [
        ("/projects/p1/artifacts", "/projects/p1/artifacts"),
        ("/projects/p1?tab=all", "/projects/p1?tab=all"),
        ("/", "/"),
        ("//evil.example", "/"),  # protocol-relative — leaves the origin
        ("//evil.example/steal", "/"),
        ("https://evil.example", "/"),
        ("evil.example", "/"),
        ("", "/"),
        # A backslash is *kept* — the guard only rejects "//". It cannot leave
        # the origin anyway, because the redirect quotes it; the emitted
        # Location is asserted in test_callback.py.
        ("/\\evil.example", "/\\evil.example"),
    ],
)
async def test_authorize_next_is_reduced_to_a_same_origin_path(
    stand: OAuthStand, requested: str, stored: str
) -> None:
    claims = await _open_flow(stand, next=requested)

    assert claims["next"] == stored


@pytest.mark.integration
async def test_authorize_next_defaults_to_the_root_when_absent(
    stand: OAuthStand,
) -> None:
    claims = await _open_flow(stand)

    assert claims["next"] == "/"


@pytest.mark.integration
async def test_authorize_cookie_is_bound_to_the_provider_that_started_it(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(fallback_country="US")

    claims = await _open_flow(stand, provider="github")

    assert claims["provider"] == "github"


@pytest.mark.integration
async def test_authorize_russian_client_cannot_start_a_foreign_provider(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(_authorize_url("google"))

    assert response.status_code == 302
    assert response.headers["location"] == (
        "/login?error=provider_not_available_in_region"
    )
    # No flow was opened, so there is no cookie to set — and nothing to delete
    # either: a stray Set-Cookie here would wipe a flow started in another tab.
    assert cookie_header(response, FLOW_COOKIE) is None
    assert stand.providers["google"].authorize_calls == []


@pytest.mark.integration
async def test_authorize_russian_client_can_start_the_russian_provider(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(_authorize_url("yandex"))

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://yandex.example/")


@pytest.mark.integration
@pytest.mark.parametrize("provider", ["google", "github", "yandex"])
async def test_authorize_client_outside_russia_can_start_any_provider(
    stand_factory: StandFactory, provider: str
) -> None:
    stand = await stand_factory(fallback_country="US")

    response = await stand.client.get(_authorize_url(provider))

    assert response.status_code == 302
    assert response.headers["location"].startswith(f"https://{provider}.example/")


@pytest.mark.integration
async def test_authorize_eleventh_start_within_the_window_is_rejected(
    stand: OAuthStand,
) -> None:
    statuses = [
        (await stand.client.get(_authorize_url("yandex"))).status_code
        for _ in range(10)
    ]
    response = await stand.client.get(_authorize_url("yandex"))

    assert statuses == [302] * 10
    assert response.status_code == 429
    assert response.json()["detail"] == "Слишком много запросов, попробуйте позже"
    assert int(response.headers["retry-after"]) > 0


@pytest.mark.integration
async def test_authorize_rate_limited_start_does_not_touch_the_flow_cookie(
    stand: OAuthStand,
) -> None:
    # 429 is not a terminal branch of the flow: one extra click must not be
    # able to kill a login already in progress.
    for _ in range(10):
        await stand.client.get(_authorize_url("yandex"))

    response = await stand.client.get(_authorize_url("yandex"))

    assert response.status_code == 429
    assert cookie_header(response, FLOW_COOKIE) is None


@pytest.mark.integration
async def test_authorize_budget_is_spent_before_the_provider_is_called(
    stand: OAuthStand,
) -> None:
    for _ in range(11):
        await stand.client.get(_authorize_url("yandex"))

    assert len(stand.yandex.authorize_calls) == 10


@pytest.mark.integration
async def test_authorize_budget_is_counted_per_client_address(
    stand_factory: StandFactory,
) -> None:
    # The brief says 10/min *per IP*. A single shared bucket would let one
    # clicker lock every other user out of logging in, and no case could see
    # the difference while every request comes from the same test socket — so
    # this stand reads the address from a header the test controls.
    stand = await stand_factory(client_ip_source="x-real-ip")
    heavy = {"X-Real-IP": "203.0.113.10"}
    fresh = {"X-Real-IP": "198.51.100.7"}

    for _ in range(10):
        await stand.client.get(_authorize_url("yandex"), headers=heavy)
    exhausted = await stand.client.get(_authorize_url("yandex"), headers=heavy)
    other_client = await stand.client.get(_authorize_url("yandex"), headers=fresh)

    assert exhausted.status_code == 429
    assert other_client.status_code == 302


@pytest.mark.integration
async def test_authorize_geo_follows_the_database_lookup_not_the_fallback(
    stand_factory: StandFactory,
) -> None:
    # The gate here must consult the same resolver as /providers: reading the
    # configured fallback directly would keep every case green and quietly
    # stop the lookup from ever deciding anything.
    stand = await stand_factory(
        fallback_country="US", geoip_reader=geoip_reader_for({"country_code": "RU"})
    )

    response = await stand.client.get(_authorize_url("google"))

    assert response.headers["location"] == (
        "/login?error=provider_not_available_in_region"
    )
    assert stand.providers["google"].authorize_calls == []


@pytest.mark.integration
async def test_authorize_geo_lookup_can_also_lift_a_restrictive_fallback(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(
        fallback_country="RU", geoip_reader=geoip_reader_for({"country_code": "US"})
    )

    response = await stand.client.get(_authorize_url("google"))

    assert response.status_code == 302
    assert response.headers["location"].startswith("https://google.example/")


@pytest.mark.integration
async def test_authorize_lower_case_fallback_still_blocks_a_foreign_provider(
    stand_factory: StandFactory,
) -> None:
    # GEOIP_FALLBACK_COUNTRY=ru must not read as "not Russia": before the fix
    # every degraded lookup opened the foreign providers to Russian clients.
    stand = await stand_factory(fallback_country="ru", geoip_reader=None)

    response = await stand.client.get(_authorize_url("google"))

    assert response.headers["location"] == (
        "/login?error=provider_not_available_in_region"
    )
    assert stand.providers["google"].authorize_calls == []
