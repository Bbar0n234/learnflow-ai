"""Solitary-unit on the client-IP helper: which source wins, and what happens
when the configured source is not there.

``get_client_ip`` is a pure function over a request and settings, so there is
nothing to fake: the tests hand it hand-built ASGI scopes. The behaviour under
test is a trust decision — the configured source decides which bytes count as
the client address, and anything a client can write itself must not leak into
the answer through some other door.
"""

from __future__ import annotations

import pytest
from app.infra.client_ip import get_client_ip, is_health_path
from structlog.testing import capture_logs

from tests.client_ip._helpers import (
    CLIENT_SPOOF_IP,
    PROXY_APPENDED_IP,
    SOCKET_IP,
    IpSource,
    make_request,
    make_settings,
)

SPOOFED_HEADERS = {
    "X-Forwarded-For": CLIENT_SPOOF_IP,
    "X-Real-IP": CLIENT_SPOOF_IP,
}


# --- socket (default) -------------------------------------------------------


@pytest.mark.unit
def test_socket_source_ignores_client_supplied_proxy_headers() -> None:
    request = make_request(headers=SPOOFED_HEADERS)

    assert get_client_ip(request, make_settings("socket")) == SOCKET_IP


@pytest.mark.unit
def test_socket_source_without_peer_returns_unknown() -> None:
    request = make_request(client=None)

    assert get_client_ip(request, make_settings("socket")) == "unknown"


@pytest.mark.unit
def test_socket_source_is_the_default() -> None:
    request = make_request(headers=SPOOFED_HEADERS)

    assert get_client_ip(request, make_settings()) == SOCKET_IP


# --- x-real-ip (production) -------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"X-Real-IP": PROXY_APPENDED_IP}, PROXY_APPENDED_IP),
        ({"x-real-ip": PROXY_APPENDED_IP}, PROXY_APPENDED_IP),
        ({"X-Real-IP": f"  {PROXY_APPENDED_IP}  "}, PROXY_APPENDED_IP),
        ({"X-Real-IP": "2001:db8::1"}, "2001:db8::1"),
        # nginx sets the header wholesale, so whatever it holds is taken as one
        # value — the helper never splits it.
        ({"X-Real-IP": "192.0.2.7, 203.0.113.66"}, "192.0.2.7, 203.0.113.66"),
    ],
    ids=["plain", "lowercase-name", "padded", "ipv6", "not-split"],
)
def test_x_real_ip_source_takes_the_whole_header_value(
    headers: dict[str, str], expected: str
) -> None:
    request = make_request(headers=headers)

    assert get_client_ip(request, make_settings("x-real-ip")) == expected


@pytest.mark.unit
def test_x_real_ip_source_ignores_forwarded_for() -> None:
    request = make_request(
        headers={"X-Real-IP": PROXY_APPENDED_IP, "X-Forwarded-For": CLIENT_SPOOF_IP}
    )

    assert get_client_ip(request, make_settings("x-real-ip")) == PROXY_APPENDED_IP


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Real-IP": ""},
        {"X-Real-IP": "   "},
        {"X-Forwarded-For": CLIENT_SPOOF_IP},
    ],
    ids=["absent", "empty", "blank", "only-forwarded-for"],
)
def test_x_real_ip_missing_falls_back_to_socket_and_warns(
    headers: dict[str, str],
) -> None:
    request = make_request(headers=headers)

    with capture_logs() as logs:
        resolved = get_client_ip(request, make_settings("x-real-ip"))

    assert resolved == SOCKET_IP
    assert [entry["log_level"] for entry in logs] == ["warning"]


# --- x-forwarded-for (multi-proxy topologies) -------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("header", "hops", "expected"),
    [
        (f"{CLIENT_SPOOF_IP}, {PROXY_APPENDED_IP}", 1, PROXY_APPENDED_IP),
        (f"{CLIENT_SPOOF_IP}, {PROXY_APPENDED_IP}", 2, CLIENT_SPOOF_IP),
        ("203.0.113.1, 203.0.113.2, 192.0.2.9, 192.0.2.7", 2, "192.0.2.9"),
        # A client may prepend as many values as it likes; counting from the
        # right keeps the answer on the part the proxies wrote.
        (f"1.1.1.1, 2.2.2.2, 3.3.3.3, {PROXY_APPENDED_IP}", 1, PROXY_APPENDED_IP),
        (f"  {CLIENT_SPOOF_IP} ,   {PROXY_APPENDED_IP}  ", 1, PROXY_APPENDED_IP),
        (f"{CLIENT_SPOOF_IP},,{PROXY_APPENDED_IP}", 1, PROXY_APPENDED_IP),
        (f"{PROXY_APPENDED_IP},", 1, PROXY_APPENDED_IP),
    ],
    ids=[
        "nearest-proxy",
        "one-hop-further",
        "two-hops-of-four",
        "client-prefix-ignored",
        "whitespace",
        "empty-element",
        "trailing-comma",
    ],
)
def test_x_forwarded_for_source_counts_hops_from_the_right(
    header: str, hops: int, expected: str
) -> None:
    request = make_request(headers={"X-Forwarded-For": header})

    assert get_client_ip(request, make_settings("x-forwarded-for", hops)) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("headers", "hops"),
    [
        ({}, 1),
        ({"X-Forwarded-For": ""}, 1),
        ({"X-Forwarded-For": " , "}, 1),
        ({"X-Forwarded-For": PROXY_APPENDED_IP}, 2),
        ({"X-Real-IP": PROXY_APPENDED_IP}, 1),
    ],
    ids=["absent", "empty", "separators-only", "too-few-hops", "only-real-ip"],
)
def test_x_forwarded_for_insufficient_falls_back_to_socket_and_warns(
    headers: dict[str, str], hops: int
) -> None:
    request = make_request(headers=headers)

    with capture_logs() as logs:
        resolved = get_client_ip(request, make_settings("x-forwarded-for", hops))

    assert resolved == SOCKET_IP
    assert [entry["log_level"] for entry in logs] == ["warning"]


# --- the fallback warning itself --------------------------------------------


@pytest.mark.unit
def test_fallback_warning_names_source_and_path_without_header_contents() -> None:
    request = make_request(
        path="/api/auth/register",
        headers={"X-Forwarded-For": CLIENT_SPOOF_IP, "User-Agent": "curl/8.0"},
    )

    with capture_logs() as logs:
        get_client_ip(request, make_settings("x-real-ip"))

    (warning,) = logs
    assert warning["client_ip_source"] == "x-real-ip"
    assert warning["path"] == "/api/auth/register"
    assert warning["reason"]  # machine-readable cause of the fallback
    # Header values are attacker-controlled text: they stay out of the log.
    assert CLIENT_SPOOF_IP not in str(warning)


# --- health path ------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("source", ["x-real-ip", "x-forwarded-for"])
def test_health_path_falls_back_silently(source: IpSource) -> None:
    request = make_request(path="/health")

    with capture_logs() as logs:
        resolved = get_client_ip(request, make_settings(source))

    assert resolved == SOCKET_IP
    assert logs == []


@pytest.mark.unit
def test_health_path_still_honours_a_present_header() -> None:
    request = make_request(path="/health", headers={"X-Real-IP": PROXY_APPENDED_IP})

    assert get_client_ip(request, make_settings("x-real-ip")) == PROXY_APPENDED_IP


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/health", True),
        ("/health/", False),
        ("/healthz", False),
        ("/api/health", False),
        ("/", False),
    ],
)
def test_is_health_path_matches_only_the_health_endpoint(
    path: str, expected: bool
) -> None:
    assert is_health_path(path) is expected
