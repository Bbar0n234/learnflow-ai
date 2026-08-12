"""GitHub's two deviations from the shared provider contract.

GitHub answers a rejected code with HTTP 200 and an ``error`` field in the body,
so the client cannot lean on the status line; and it hides the email behind a
second endpoint, which is optional enrichment rather than part of the login. The
suite pins both: a 200-shaped refusal must still become ``OAuthProviderError``,
and every way the email add-on can fail must degrade to ``email=None`` while the
login itself goes through.

Naming: cases are named after the GitHub method under test where there is one
(``exchange_code``, ``fetch_profile``) and after the behaviour where the unit is
the hidden-email add-on — a deliberate deviation from
``test_<unit>_<condition>_<expected>`` for readability.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from app.infra.oauth.exceptions import OAuthProviderError
from app.infra.oauth.github import GitHubOAuthProvider

from tests.oauth._helpers import Wire

TOKEN_URL = "https://github.com/login/oauth/access_token"
PROFILE_URL = "https://api.github.com/user"
EMAILS_URL = "https://api.github.com/user/emails"

REDIRECT_URI = "http://localhost:5173/api/auth/oauth/github/callback"


def _provider(wire: Wire) -> GitHubOAuthProvider:
    return GitHubOAuthProvider(
        client_id="client-id-1",
        client_secret="client-secret-1",
        http_client=wire.client(),
    )


def _profile_wire(
    profile: dict[str, Any], emails: httpx.Response | Exception | None = None
) -> Wire:
    routes: dict[str, httpx.Response | Exception] = {
        PROFILE_URL: httpx.Response(200, json=profile)
    }
    if emails is not None:
        routes[EMAILS_URL] = emails
    return Wire(routes)


@pytest.mark.unit
async def test_exchange_code_asks_for_json_rather_than_the_default_form_body() -> None:
    # Without this header GitHub answers form-urlencoded and the JSON parse
    # would fail on a perfectly successful exchange.
    wire = Wire({TOKEN_URL: httpx.Response(200, json={"access_token": "gho_token"})})

    await _provider(wire).exchange_code(
        code="auth-code", verifier="verifier-1", redirect_uri=REDIRECT_URI
    )

    assert wire.request_to(TOKEN_URL).headers["accept"] == "application/json"


@pytest.mark.unit
async def test_exchange_code_rejects_an_error_body_returned_with_status_200() -> None:
    # GitHub's documented shape for a bad code/redirect_uri/secret: HTTP 200
    # with the failure in the body. Treating it as success would hand the
    # profile call an empty token.
    wire = Wire(
        {
            TOKEN_URL: httpx.Response(
                200,
                json={
                    "error": "bad_verification_code",
                    "error_description": "The code passed is incorrect or expired.",
                },
            )
        }
    )

    with pytest.raises(OAuthProviderError):
        await _provider(wire).exchange_code(
            code="stale-code", verifier="verifier-1", redirect_uri=REDIRECT_URI
        )


@pytest.mark.unit
async def test_fetch_profile_converts_the_numeric_account_id_to_a_string() -> None:
    # GitHub is the only provider whose id arrives as a JSON number; the stored
    # provider_account_id is text for every provider.
    wire = _profile_wire({"id": 583231, "login": "octocat", "email": "o@github.com"})

    profile = await _provider(wire).fetch_profile(token="gho_token")

    assert profile.provider_account_id == "583231"


@pytest.mark.unit
async def test_fetch_profile_rejects_a_non_numeric_account_id() -> None:
    wire = _profile_wire({"id": None, "login": "octocat", "email": "o@github.com"})

    with pytest.raises(OAuthProviderError):
        await _provider(wire).fetch_profile(token="gho_token")


@pytest.mark.unit
async def test_hidden_email_is_taken_from_the_primary_verified_address() -> None:
    wire = _profile_wire(
        {"id": 1, "login": "octocat", "email": None},
        emails=httpx.Response(
            200,
            json=[
                {"email": "secondary@github.com", "primary": False, "verified": True},
                {"email": "primary@github.com", "primary": True, "verified": True},
            ],
        ),
    )

    profile = await _provider(wire).fetch_profile(token="gho_token")

    assert profile.email == "primary@github.com"
    # The add-on request is authenticated the same way as the profile one;
    # a wrong scheme here would silently cost every hidden email.
    assert wire.request_to(EMAILS_URL).headers["authorization"] == "Bearer gho_token"


@pytest.mark.unit
async def test_hidden_email_falls_back_to_any_verified_address() -> None:
    # The primary address may be unverified; an unverified address is never
    # taken, because nothing downstream re-verifies it.
    wire = _profile_wire(
        {"id": 1, "login": "octocat", "email": None},
        emails=httpx.Response(
            200,
            json=[
                {"email": "unverified@github.com", "primary": True, "verified": False},
                {"email": "verified@github.com", "primary": False, "verified": True},
            ],
        ),
    )

    profile = await _provider(wire).fetch_profile(token="gho_token")

    assert profile.email == "verified@github.com"


@pytest.mark.unit
@pytest.mark.parametrize(
    "emails",
    [
        httpx.Response(200, json=[]),
        httpx.Response(
            200,
            json=[{"email": "u@github.com", "primary": True, "verified": False}],
        ),
        httpx.Response(200, json={"message": "Not Found"}),
        httpx.Response(200, text="not json"),
        httpx.Response(403, json={"message": "Missing scope user:email"}),
        httpx.Response(500, json={"message": "boom"}),
    ],
    ids=["empty", "unverified-only", "not-a-list", "not-json", "forbidden", "server"],
)
async def test_email_lookup_failure_leaves_the_login_intact(
    emails: httpx.Response,
) -> None:
    # The email is enrichment, not identity: a broken /user/emails must not
    # cost the user their login.
    wire = _profile_wire({"id": 1, "login": "octocat", "email": None}, emails=emails)

    profile = await _provider(wire).fetch_profile(token="gho_token")

    assert profile.email is None
    assert profile.provider_account_id == "1"
    assert profile.display_name == "octocat"


@pytest.mark.unit
async def test_email_lookup_transport_failure_leaves_the_login_intact() -> None:
    wire = _profile_wire(
        {"id": 1, "login": "octocat", "email": None},
        emails=httpx.ReadTimeout("read timed out"),
    )

    profile = await _provider(wire).fetch_profile(token="gho_token")

    assert profile.email is None


@pytest.mark.unit
async def test_a_visible_email_is_used_without_a_second_request() -> None:
    # /user/emails is not in the route table, so any call to it fails the test.
    wire = _profile_wire({"id": 1, "login": "octocat", "email": "o@github.com"})

    profile = await _provider(wire).fetch_profile(token="gho_token")

    assert profile.email == "o@github.com"
    assert wire.urls_called() == [PROFILE_URL]
