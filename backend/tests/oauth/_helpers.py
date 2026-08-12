"""Helpers for driving the OAuth endpoints and provider clients in tests.

Pure functions plus three stand-ins, all sitting on an *external* boundary and
nothing else: ``FakeProvider`` replaces the network call to an identity provider
(routes -> service -> repository -> PostgreSQL stay real underneath), ``Wire``
replaces the wire itself for the real provider clients via
``httpx.MockTransport``, and ``StubGeoipReader`` replaces the MMDB file. Cookies
are read off the raw ``Set-Cookie`` headers rather than the client jar, because
several cases assert on *deletion* (``Max-Age=0``), which the jar swallows.
"""

from __future__ import annotations

import base64
import hashlib
from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
from typing import Any, cast
from urllib.parse import parse_qs

import httpx
import jwt
import maxminddb
from app.infra.oauth.base import OAuthProfile
from httpx import Response
from maxminddb.types import Record

JWT_SECRET = "test-secret"
REDIRECT_BASE_URL = "http://localhost:5173"
FLOW_ALGORITHM = "HS256"


# --------------------------------------------------------------------------
# Provider stand-in (network boundary)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorizeCall:
    state: str
    challenge: str
    redirect_uri: str


@dataclass(frozen=True)
class ExchangeCall:
    code: str
    verifier: str
    redirect_uri: str


@dataclass
class FakeProvider:
    """A provider whose HTTP calls are replaced by recorded in-memory answers.

    Structurally satisfies ``app.infra.oauth.base.OAuthProvider``. Calls are
    recorded so tests can assert *what the route handed the provider* (state,
    PKCE challenge, redirect_uri, verifier) — that hand-off is the observable
    contract between the route and the outside world.
    """

    name: str
    profile: OAuthProfile | None = None
    exchange_error: Exception | None = None
    profile_error: Exception | None = None
    authorize_calls: list[AuthorizeCall] = field(default_factory=list)
    exchange_calls: list[ExchangeCall] = field(default_factory=list)
    profile_tokens: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.profile is None:
            self.profile = OAuthProfile(
                provider=self.name,
                provider_account_id=f"{self.name}-account-1",
                email=f"{self.name}@example.com",
                display_name=f"{self.name}-user",
            )

    def authorize_url(self, *, state: str, challenge: str, redirect_uri: str) -> str:
        self.authorize_calls.append(AuthorizeCall(state, challenge, redirect_uri))
        return (
            f"https://{self.name}.example/authorize"
            f"?state={state}&code_challenge={challenge}"
        )

    async def exchange_code(
        self, *, code: str, verifier: str, redirect_uri: str
    ) -> str:
        self.exchange_calls.append(ExchangeCall(code, verifier, redirect_uri))
        if self.exchange_error is not None:
            raise self.exchange_error
        return f"{self.name}-access-token"

    async def fetch_profile(self, *, token: str) -> OAuthProfile:
        self.profile_tokens.append(token)
        if self.profile_error is not None:
            raise self.profile_error
        assert self.profile is not None  # set in __post_init__
        return self.profile


def all_fake_providers() -> dict[str, FakeProvider]:
    """The registry as a fully configured deployment would build it."""
    return {name: FakeProvider(name) for name in ("yandex", "google", "github")}


# --------------------------------------------------------------------------
# httpx wire double for the real provider clients
# --------------------------------------------------------------------------


class Wire:
    """The provider's side of the wire: answers by URL and records the calls.

    Backs an ``httpx.AsyncClient`` through ``MockTransport``, so the provider
    clients run their real request-building and response-parsing code with no
    socket in sight. A URL that is not in the table fails the test loudly —
    a client calling the wrong endpoint must not look healthy. A mapped
    ``Exception`` is raised instead of answered, which is how transport
    failures (timeouts, connection errors) are staged.
    """

    def __init__(self, routes: dict[str, httpx.Response | Exception]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url not in self.routes:
            raise AssertionError(f"unexpected request to {url}")
        answer = self.routes[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self))

    def request_to(self, url: str) -> httpx.Request:
        for request in self.requests:
            if str(request.url) == url:
                return request
        raise AssertionError(f"no request was made to {url}")

    def form_sent_to(self, url: str) -> dict[str, str]:
        """Form-urlencoded body of the request to ``url``, flattened."""
        body = self.request_to(url).content.decode()
        return {key: values[0] for key, values in parse_qs(body).items()}

    def urls_called(self) -> list[str]:
        return [str(request.url) for request in self.requests]


# --------------------------------------------------------------------------
# GeoIP reader stand-in
# --------------------------------------------------------------------------


class StubGeoipReader:
    """MMDB reader stand-in: hands back one record, or raises like the real one.

    ``maxminddb.Reader.get`` raises ``ValueError`` when its argument is not a
    parsable IP address — the literal ``"unknown"`` that ``get_client_ip``
    returns when there is no client at all. The stub reproduces that so the
    fail-closed branch is exercised, not assumed.
    """

    def __init__(self, record: Record | None) -> None:
        self.record = record
        self.queried: list[str] = []

    def get(self, ip: str) -> Record | None:
        self.queried.append(ip)
        if ip == "unknown":
            raise ValueError(f"{ip!r} does not appear to be an IPv4 or IPv6 address")
        return self.record


class CorruptGeoipReader:
    """A reader over a corrupt-but-openable MMDB: every lookup blows up.

    ``open_reader`` only reads the header, so a truncated or damaged database
    opens successfully and fails on the first ``get`` with
    ``maxminddb.InvalidDatabaseError`` — a ``RuntimeError``, not a
    ``ValueError``, which is why it needs its own stand-in.
    """

    def __init__(self) -> None:
        self.queried: list[str] = []

    def get(self, ip: str) -> Record | None:
        self.queried.append(ip)
        raise maxminddb.InvalidDatabaseError(
            "Invalid record pointer in the search tree"
        )


def geoip_reader_for(record: Record | None) -> maxminddb.Reader:
    """A stub reader typed as the real one for call sites that require it."""
    return cast("maxminddb.Reader", StubGeoipReader(record))


def corrupt_geoip_reader() -> maxminddb.Reader:
    """A reader whose lookups raise like a corrupt database's do."""
    return cast("maxminddb.Reader", CorruptGeoipReader())


# --------------------------------------------------------------------------
# Cookies
# --------------------------------------------------------------------------


def find_set_cookie(raw_headers: Sequence[str], name: str) -> str | None:
    """Raw ``Set-Cookie`` header for ``name`` among ``raw_headers``."""
    for raw in raw_headers:
        if raw.split("=", 1)[0].strip() == name:
            return raw
    return None


def cookie_header(response: Response, name: str) -> str | None:
    """Raw ``Set-Cookie`` header for ``name``, or ``None`` if not set."""
    return find_set_cookie(response.headers.get_list("set-cookie"), name)


def cookie_value(response: Response, name: str) -> str | None:
    raw = cookie_header(response, name)
    if raw is None:
        return None
    jar: SimpleCookie = SimpleCookie()
    jar.load(raw)
    return jar[name].value


def cookie_attributes(raw_header: str) -> dict[str, str]:
    """Cookie attributes lowercased; valueless flags map to an empty string."""
    attrs: dict[str, str] = {}
    for part in raw_header.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        attrs[key.lower()] = value
    return attrs


def is_deleted_cookie(response: Response, name: str) -> bool:
    """True when the response actively expires ``name`` (empty value, Max-Age=0)."""
    raw = cookie_header(response, name)
    if raw is None:
        return False
    return cookie_value(response, name) == "" and (
        cookie_attributes(raw).get("max-age") == "0"
    )


# --------------------------------------------------------------------------
# oauth_flow cookie
# --------------------------------------------------------------------------


def make_flow_cookie(
    *,
    state: str = "state-123",
    verifier: str = "verifier-abc",
    provider: str = "yandex",
    next_path: str = "/",
    jwt_secret: str = JWT_SECRET,
    expires_in: int = 600,
) -> str:
    """Builds the ``oauth_flow`` cookie the way a browser would carry it back.

    Written with ``jwt.encode`` directly (not through ``encode_flow_cookie``)
    so a test can hand the callback an *expired*, *foreign-provider* or
    *wrong-secret* cookie — inputs the production encoder cannot produce.
    """
    payload: dict[str, Any] = {
        "state": state,
        "verifier": verifier,
        "provider": provider,
        "next": next_path,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in),
    }
    return jwt.encode(payload, jwt_secret, algorithm=FLOW_ALGORITHM)


def flow_claims(token: str, jwt_secret: str = JWT_SECRET) -> dict[str, Any]:
    claims: dict[str, Any] = jwt.decode(token, jwt_secret, algorithms=[FLOW_ALGORITHM])
    return claims


def s256_challenge(verifier: str) -> str:
    """PKCE S256 challenge, recomputed from RFC 7636 § 4.2 inside the test."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# --------------------------------------------------------------------------
# structlog assertions
# --------------------------------------------------------------------------


def security_events(
    logs: Sequence[MutableMapping[str, Any]],
) -> list[MutableMapping[str, Any]]:
    """SIEM events among captured structlog entries (``security_event=True``)."""
    return [entry for entry in logs if entry.get("security_event") is True]


def event_types(logs: Sequence[MutableMapping[str, Any]]) -> list[str]:
    return [str(entry["event_type"]) for entry in security_events(logs)]
