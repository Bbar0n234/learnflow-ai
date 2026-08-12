"""The three provider clients against a doubled wire (``httpx.MockTransport``).

Everything the three have in common is stated once and parametrised over them:
the authorization URL they build, the token they get back, the profile they
normalise, and — the part that matters for the callback — that every kind of
provider failure (an HTTP error status, a dead connection, a body that does not
say what it should) collapses into a single ``OAuthProviderError``. That single
exception is what the callback turns into ``provider_unavailable``, so a client
that leaked ``KeyError`` or ``httpx.ConnectError`` instead would surface as a
500 rather than a redirect.

Provider-specific quirks that are not shared live next door in
``test_github_provider.py``.

Naming: the ``test_<unit>_<condition>_<expected>`` convention is kept with the
unit first (``authorize_url`` / ``exchange_code`` / ``fetch_profile``) and the
condition and expectation spelled as prose rather than as identifiers — a
deliberate deviation for readability, applied consistently across this scope.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from app.infra.oauth.base import OAuthProvider
from app.infra.oauth.exceptions import OAuthProviderError
from app.infra.oauth.github import GitHubOAuthProvider
from app.infra.oauth.google import GoogleOAuthProvider
from app.infra.oauth.yandex import YandexOAuthProvider

from tests.oauth._helpers import Wire, s256_challenge

CLIENT_ID = "client-id-1"
CLIENT_SECRET = "client-secret-1"
REDIRECT_URI = "http://localhost:5173/api/auth/oauth/{provider}/callback"


@dataclass(frozen=True)
class ProviderCase:
    """One provider's wire contract, as documented by its research notes."""

    name: str
    build: Callable[[httpx.AsyncClient], OAuthProvider]
    authorize_endpoint: str
    token_endpoint: str
    profile_endpoint: str
    profile_payload: dict[str, Any]
    account_id: str
    email: str
    display_name: str
    # The two values that look shared but are not, and that a provider
    # answers 401/403 to when they are wrong: the Authorization scheme of
    # the profile call, and the scope asked for at authorize time (``None``
    # where the provider needs none).
    auth_scheme: str
    scope: str | None


def _yandex(http_client: httpx.AsyncClient) -> OAuthProvider:
    return YandexOAuthProvider(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http_client=http_client
    )


def _google(http_client: httpx.AsyncClient) -> OAuthProvider:
    return GoogleOAuthProvider(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http_client=http_client
    )


def _github(http_client: httpx.AsyncClient) -> OAuthProvider:
    return GitHubOAuthProvider(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET, http_client=http_client
    )


CASES = [
    ProviderCase(
        name="yandex",
        build=_yandex,
        authorize_endpoint="https://oauth.yandex.ru/authorize",
        token_endpoint="https://oauth.yandex.ru/token",
        profile_endpoint="https://login.yandex.ru/info",
        profile_payload={
            "id": "1130000012345",
            "login": "ivan",
            "default_email": "ivan@yandex.ru",
        },
        account_id="1130000012345",
        email="ivan@yandex.ru",
        display_name="ivan",
        auth_scheme="OAuth",  # Яндекс ID does not accept "Bearer"
        scope=None,  # scopes come from the app registration, not the URL
    ),
    ProviderCase(
        name="google",
        build=_google,
        authorize_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        profile_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
        profile_payload={
            "sub": "104512340987",
            "email": "anna@gmail.com",
            "given_name": "Anna",
        },
        account_id="104512340987",
        email="anna@gmail.com",
        display_name="Anna",
        auth_scheme="Bearer",
        scope="openid email profile",  # without it userinfo answers 403
    ),
    ProviderCase(
        name="github",
        build=_github,
        authorize_endpoint="https://github.com/login/oauth/authorize",
        token_endpoint="https://github.com/login/oauth/access_token",
        profile_endpoint="https://api.github.com/user",
        profile_payload={"id": 4242, "login": "octo", "email": "octo@github.com"},
        account_id="4242",
        email="octo@github.com",
        display_name="octo",
        auth_scheme="Bearer",
        scope="user:email",  # the hidden-email lookup stands on this scope
    ),
]

CASE_IDS = [case.name for case in CASES]


def _redirect_uri(case: ProviderCase) -> str:
    return REDIRECT_URI.format(provider=case.name)


def _token_response(case: ProviderCase, payload: Any, status: int = 200) -> Wire:
    return Wire({case.token_endpoint: httpx.Response(status, json=payload)})


def _profile_response(case: ProviderCase, payload: Any, status: int = 200) -> Wire:
    return Wire({case.profile_endpoint: httpx.Response(status, json=payload)})


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_authorize_url_carries_state_and_an_s256_challenge(
    case: ProviderCase,
) -> None:
    verifier = "verifier-under-test"
    provider = case.build(Wire({}).client())

    url = provider.authorize_url(
        state="state-42",
        challenge=s256_challenge(verifier),
        redirect_uri=_redirect_uri(case),
    )

    split = urlsplit(url)
    params = {key: values[0] for key, values in parse_qs(split.query).items()}
    assert f"{split.scheme}://{split.netloc}{split.path}" == case.authorize_endpoint
    assert params["response_type"] == "code"
    assert params["client_id"] == CLIENT_ID
    assert params["redirect_uri"] == _redirect_uri(case)
    assert params["state"] == "state-42"
    assert params["code_challenge"] == s256_challenge(verifier)
    assert params["code_challenge_method"] == "S256"
    # The scope is load-bearing where it exists and must not be requested
    # where the provider has none: a lost or mistyped scope is a green CI and
    # a login that dies at the profile call.
    assert params.get("scope") == case.scope


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_exchange_code_returns_the_access_token(case: ProviderCase) -> None:
    wire = _token_response(case, {"access_token": "provider-token", "expires_in": 3600})

    token = await case.build(wire.client()).exchange_code(
        code="auth-code", verifier="verifier-1", redirect_uri=_redirect_uri(case)
    )

    assert token == "provider-token"
    form = wire.form_sent_to(case.token_endpoint)
    # The provider re-checks redirect_uri and (where supported) the verifier
    # against what it saw at the authorize step — both must travel here.
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "auth-code"
    assert form["redirect_uri"] == _redirect_uri(case)
    assert form["code_verifier"] == "verifier-1"
    assert form["client_id"] == CLIENT_ID
    assert form["client_secret"] == CLIENT_SECRET


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize("status", [400, 401, 500, 503])
async def test_exchange_code_turns_an_error_status_into_a_provider_error(
    case: ProviderCase, status: int
) -> None:
    wire = _token_response(case, {"error": "invalid_grant"}, status=status)

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).exchange_code(
            code="auth-code", verifier="verifier-1", redirect_uri=_redirect_uri(case)
        )


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize(
    "failure",
    [
        httpx.ConnectTimeout("timed out"),
        httpx.ConnectError("connection refused"),
        httpx.ReadTimeout("read timed out"),
    ],
    ids=["connect-timeout", "connect-error", "read-timeout"],
)
async def test_exchange_code_turns_a_dead_connection_into_a_provider_error(
    case: ProviderCase, failure: Exception
) -> None:
    wire = Wire({case.token_endpoint: failure})

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).exchange_code(
            code="auth-code", verifier="verifier-1", redirect_uri=_redirect_uri(case)
        )


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize(
    "payload",
    [{}, {"access_token": ""}, {"access_token": 12345}, {"token": "wrong-key"}],
    ids=["empty", "blank-token", "non-string-token", "wrong-key"],
)
async def test_exchange_code_turns_a_malformed_body_into_a_provider_error(
    case: ProviderCase, payload: dict[str, Any]
) -> None:
    wire = _token_response(case, payload)

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).exchange_code(
            code="auth-code", verifier="verifier-1", redirect_uri=_redirect_uri(case)
        )


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_exchange_code_survives_a_body_that_is_not_json(
    case: ProviderCase,
) -> None:
    wire = Wire({case.token_endpoint: httpx.Response(200, text="<html>oops</html>")})

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).exchange_code(
            code="auth-code", verifier="verifier-1", redirect_uri=_redirect_uri(case)
        )


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_profile_normalises_the_provider_payload(
    case: ProviderCase,
) -> None:
    wire = _profile_response(case, case.profile_payload)

    profile = await case.build(wire.client()).fetch_profile(token="provider-token")

    assert profile.provider == case.name
    assert profile.provider_account_id == case.account_id
    assert profile.email == case.email
    assert profile.display_name == case.display_name
    # The account id crosses the abstraction as a string for every provider,
    # whatever the provider's own JSON type is.
    assert isinstance(profile.provider_account_id, str)


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_profile_sends_the_access_token_under_the_providers_scheme(
    case: ProviderCase,
) -> None:
    wire = _profile_response(case, case.profile_payload)

    await case.build(wire.client()).fetch_profile(token="provider-token")

    authorization = wire.request_to(case.profile_endpoint).headers["authorization"]
    # The scheme is not interchangeable — Яндекс rejects "Bearer", Google and
    # GitHub reject "OAuth" — and getting it wrong breaks every login with a
    # 401 that the callback reports as provider_unavailable.
    assert authorization == f"{case.auth_scheme} provider-token"


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
@pytest.mark.parametrize("status", [401, 403, 500])
async def test_fetch_profile_turns_an_error_status_into_a_provider_error(
    case: ProviderCase, status: int
) -> None:
    wire = _profile_response(case, {"error": "bad token"}, status=status)

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).fetch_profile(token="provider-token")


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_profile_turns_a_dead_connection_into_a_provider_error(
    case: ProviderCase,
) -> None:
    wire = Wire({case.profile_endpoint: httpx.ReadTimeout("read timed out")})

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).fetch_profile(token="provider-token")


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_profile_without_an_account_id_is_a_provider_error(
    case: ProviderCase,
) -> None:
    # No account id means we never learned *who* logged in — the one thing the
    # whole flow exists to establish, so it can never degrade to a partial
    # profile.
    payload = {k: v for k, v in case.profile_payload.items() if k not in {"id", "sub"}}
    wire = _profile_response(case, payload)

    with pytest.raises(OAuthProviderError):
        await case.build(wire.client()).fetch_profile(token="provider-token")


@pytest.mark.unit
@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
async def test_fetch_profile_tolerates_a_missing_display_name(
    case: ProviderCase,
) -> None:
    # An absent optional field must not fail the login: the service falls back
    # to a generated user name.
    payload = {
        k: v
        for k, v in case.profile_payload.items()
        if k not in {"login", "given_name"}
    }
    wire = _profile_response(case, payload)

    profile = await case.build(wire.client()).fetch_profile(token="provider-token")

    assert profile.display_name is None
    assert profile.provider_account_id == case.account_id
