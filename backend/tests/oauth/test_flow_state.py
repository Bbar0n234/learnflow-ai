"""The ``oauth_flow`` cookie: solitary-unit on the signed carrier of the flow.

This cookie is the entire server-side memory of a flow (design-brief § Хранение
state), so the suite is written from the attacker's side: every way a cookie can
arrive wrong — forged signature, expired, minted for another provider, missing
claims — must collapse into a single ``None``, which the callback reads as one
``flow_expired`` branch. The ``next`` guard is checked here too, because it is
the only thing standing between the redirect and an open redirect.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from app.config import Settings
from app.infra.oauth.flow_state import (
    COOKIE_NAME,
    decode_flow_cookie,
    delete_flow_cookie,
    encode_flow_cookie,
    is_safe_next_path,
    set_flow_cookie,
)
from fastapi import Response

from tests.oauth._helpers import (
    JWT_SECRET,
    cookie_attributes,
    find_set_cookie,
    make_flow_cookie,
)
from tests.oauth.conftest import build_settings


def _encode(**overrides: object) -> str:
    payload: dict[str, object] = {
        "state": "state-1",
        "verifier": "verifier-1",
        "provider": "yandex",
        "next": "/",
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    payload.update(overrides)
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    ["/", "/projects", "/projects/p1/artifacts?tab=all", "/login#top", "/a//b"],
)
def test_is_safe_next_path_accepts_relative_paths(path: str) -> None:
    assert is_safe_next_path(path) is True


@pytest.mark.unit
@pytest.mark.parametrize("path", ["/\\evil.example", "/\\/evil.example"])
def test_is_safe_next_path_lets_a_backslash_through(path: str) -> None:
    # Pinned as a *known* answer, not as an endorsement: the guard only looks
    # at "//", so a backslash form reaches the response layer. It is not an
    # open redirect because the redirect quotes it (%5C) before the browser
    # ever sees an authority — that outcome is asserted on the emitted
    # Location in test_callback.py, which is where the security property
    # actually lives. Should the guard ever start rejecting it, this row and
    # that one change together.
    assert is_safe_next_path(path) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "path",
    [
        "//evil.example",  # protocol-relative URL — browsers leave the origin
        "//evil.example/callback",
        "https://evil.example",
        "http://evil.example",
        "evil.example",
        "",
    ],
)
def test_is_safe_next_path_rejects_anything_that_can_leave_the_origin(
    path: str,
) -> None:
    assert is_safe_next_path(path) is False


@pytest.mark.unit
def test_encode_then_decode_returns_the_same_flow() -> None:
    token = encode_flow_cookie(
        state="state-xyz",
        verifier="verifier-xyz",
        provider="google",
        next_path="/projects/p1",
        jwt_secret=JWT_SECRET,
    )

    flow = decode_flow_cookie(token, provider="google", jwt_secret=JWT_SECRET)

    assert flow is not None
    assert (flow.state, flow.verifier, flow.provider, flow.next) == (
        "state-xyz",
        "verifier-xyz",
        "google",
        "/projects/p1",
    )


@pytest.mark.unit
def test_decode_rejects_cookie_minted_for_another_provider() -> None:
    # A cookie from a yandex flow must not authorise a google callback: the
    # provider is part of what the signature binds together.
    token = make_flow_cookie(provider="yandex")

    assert decode_flow_cookie(token, provider="google", jwt_secret=JWT_SECRET) is None


@pytest.mark.unit
def test_decode_rejects_cookie_signed_with_another_secret() -> None:
    token = make_flow_cookie(jwt_secret="not-the-app-secret")

    assert decode_flow_cookie(token, provider="yandex", jwt_secret=JWT_SECRET) is None


@pytest.mark.unit
def test_decode_rejects_expired_cookie() -> None:
    token = make_flow_cookie(expires_in=-1)

    assert decode_flow_cookie(token, provider="yandex", jwt_secret=JWT_SECRET) is None


@pytest.mark.unit
@pytest.mark.parametrize("missing", ["state", "verifier", "next"])
def test_decode_rejects_cookie_with_a_missing_claim(missing: str) -> None:
    payload = {
        "state": "state-1",
        "verifier": "verifier-1",
        "provider": "yandex",
        "next": "/",
        "exp": datetime.now(UTC) + timedelta(minutes=10),
    }
    del payload[missing]
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    assert decode_flow_cookie(token, provider="yandex", jwt_secret=JWT_SECRET) is None


@pytest.mark.unit
@pytest.mark.parametrize("token", ["", "not-a-jwt", "a.b.c"])
def test_decode_rejects_garbage(token: str) -> None:
    assert decode_flow_cookie(token, provider="yandex", jwt_secret=JWT_SECRET) is None


@pytest.mark.unit
def test_decode_accepts_a_cookie_that_has_not_expired_yet() -> None:
    # Guards the expiry check against being inverted: a live cookie must pass.
    token = _encode(exp=datetime.now(UTC) + timedelta(seconds=1))

    assert decode_flow_cookie(token, provider="yandex", jwt_secret=JWT_SECRET)


@pytest.mark.unit
@pytest.mark.parametrize("secure_cookies", [True, False])
def test_set_flow_cookie_is_scoped_and_shielded_from_javascript(
    secure_cookies: bool,
) -> None:
    settings: Settings = build_settings(secure_cookies=secure_cookies)
    response = Response()

    set_flow_cookie(response, "token-value", settings)

    raw = find_set_cookie(response.headers.getlist("set-cookie"), COOKIE_NAME)
    assert raw is not None
    attrs = cookie_attributes(raw)
    assert attrs["path"] == "/api/auth/oauth"
    assert attrs["max-age"] == "600"
    assert attrs["samesite"].lower() == "lax"  # survives the top-level redirect
    assert "httponly" in attrs
    assert ("secure" in attrs) is secure_cookies


@pytest.mark.unit
def test_delete_flow_cookie_expires_it_on_the_same_path() -> None:
    settings = build_settings()
    response = Response()

    delete_flow_cookie(response, settings)

    raw = find_set_cookie(response.headers.getlist("set-cookie"), COOKIE_NAME)
    assert raw is not None
    attrs = cookie_attributes(raw)
    # Same Path as when it was set — a mismatch would leave the browser holding
    # a live flow cookie after a terminal branch.
    assert attrs["path"] == "/api/auth/oauth"
    assert attrs["max-age"] == "0"
