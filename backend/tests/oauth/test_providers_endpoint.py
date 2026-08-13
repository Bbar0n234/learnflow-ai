"""``GET /api/auth/providers`` — what the login page is allowed to offer.

This endpoint is the whole geo policy as the browser sees it, so the suite
states the rule from both sides: a Russian client is offered the intersection of
the Russian allow-list with the providers that are actually configured (never a
button that would 404), everyone else is offered every configured provider, and
the password form is offered unconditionally. The country itself is taken from
the real ``resolve_country``, either through the fallback or through a stubbed
MMDB lookup, so a regression that stopped consulting geo at all would show up
here.

Naming: the unit is the endpoint itself, named once in the module, so the cases
spell out condition and expectation in prose rather than repeating it — a
deliberate deviation from ``test_<unit>_<condition>_<expected>``.
"""

from __future__ import annotations

import pytest

from tests.oauth._helpers import FakeProvider, geoip_reader_for
from tests.oauth.conftest import OAuthStand, StandFactory

PROVIDERS_URL = "/api/auth/providers"


def _registry(*names: str) -> dict[str, FakeProvider]:
    return {name: FakeProvider(name) for name in names}


@pytest.mark.integration
async def test_russian_client_is_offered_only_the_russian_provider(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(PROVIDERS_URL)

    assert response.status_code == 200
    assert response.json() == {"providers": ["yandex"], "password": True}


@pytest.mark.integration
async def test_client_outside_russia_is_offered_every_active_provider(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(fallback_country="US")

    response = await stand.client.get(PROVIDERS_URL)

    assert response.status_code == 200
    assert response.json() == {
        "providers": ["github", "google", "yandex"],
        "password": True,
    }


@pytest.mark.integration
async def test_russian_client_gets_no_buttons_when_the_russian_provider_is_off(
    stand_factory: StandFactory,
) -> None:
    # The allow-list is intersected with the *configured* registry: an
    # unconfigured Yandex must leave the page with the password form alone,
    # not with a button leading straight into a 404.
    stand = await stand_factory(providers=_registry("google", "github"))

    response = await stand.client.get(PROVIDERS_URL)

    assert response.json() == {"providers": [], "password": True}


@pytest.mark.integration
async def test_no_configured_provider_leaves_the_password_form_alone(
    stand_factory: StandFactory,
) -> None:
    stand = await stand_factory(providers={}, fallback_country="US")

    response = await stand.client.get(PROVIDERS_URL)

    assert response.json() == {"providers": [], "password": True}


@pytest.mark.integration
async def test_composition_follows_the_database_lookup_not_only_the_fallback(
    stand_factory: StandFactory,
) -> None:
    # Fallback says RU, the database says US: the answer must come from the
    # lookup — otherwise the geo gate would be decided by configuration alone.
    stand = await stand_factory(
        fallback_country="RU", geoip_reader=geoip_reader_for({"country_code": "US"})
    )

    response = await stand.client.get(PROVIDERS_URL)

    assert response.json()["providers"] == ["github", "google", "yandex"]


@pytest.mark.integration
async def test_unresolvable_address_falls_back_to_the_restricted_composition(
    stand_factory: StandFactory,
) -> None:
    # A private dev address is absent from the database; the fail-closed rule
    # then applies the configured fallback, here RU.
    stand = await stand_factory(
        fallback_country="RU", geoip_reader=geoip_reader_for(None)
    )

    response = await stand.client.get(PROVIDERS_URL)

    assert response.json()["providers"] == ["yandex"]


@pytest.mark.integration
@pytest.mark.parametrize("configured", ["ru", " ru "], ids=["lower", "padded"])
async def test_a_lower_case_fallback_still_restricts_the_composition(
    stand_factory: StandFactory, configured: str
) -> None:
    # GEOIP_FALLBACK_COUNTRY=ru is a plausible thing for an operator to write,
    # and before the fix it flipped fail-closed into fail-open: every degraded
    # lookup answered a Russian client with all three providers.
    stand = await stand_factory(fallback_country=configured, geoip_reader=None)

    response = await stand.client.get(PROVIDERS_URL)

    assert response.json() == {"providers": ["yandex"], "password": True}


@pytest.mark.integration
async def test_the_answer_carries_nothing_but_the_contracted_fields(
    stand: OAuthStand,
) -> None:
    response = await stand.client.get(PROVIDERS_URL)

    assert set(response.json()) == {"providers", "password"}


@pytest.mark.integration
async def test_listing_providers_needs_no_authentication(stand: OAuthStand) -> None:
    # The stand's client carries no credentials at all — the login page calls
    # this endpoint before anyone is logged in, so a guard here would lock the
    # provider buttons behind the very login they exist to start.
    assert "authorization" not in stand.client.headers

    response = await stand.client.get(PROVIDERS_URL)

    assert response.status_code == 200
