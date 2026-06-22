"""Solitary-unit tests for the SSRF URL validator.

``validate_url`` is a pure security guard over DNS resolution: it rejects URLs
without a hostname (400), unresolvable hostnames (400), and hostnames resolving
to private/internal ranges (422). DNS is the one impure edge — we stub
``socket.getaddrinfo`` so the tests are deterministic and offline. No private IP
must ever slip through; that is the behavior under test.
"""

from __future__ import annotations

import socket

import pytest
from app.services.exceptions import InvalidURLError, SecurityPolicyViolationError
from app.services.url_validator import validate_url


def _addrinfo(*ips: str) -> list[tuple]:
    """Build ``getaddrinfo``-shaped tuples whose [4][0] is the resolved IP."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]


def _stub_resolution(monkeypatch: pytest.MonkeyPatch, *ips: str) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port, *a, **k: _addrinfo(*ips)
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "private_ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.5.5",
        "192.168.1.10",
        "169.254.0.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_validate_url_private_ip_raises_security_violation(
    monkeypatch: pytest.MonkeyPatch, private_ip: str
) -> None:
    _stub_resolution(monkeypatch, private_ip)

    with pytest.raises(SecurityPolicyViolationError) as exc:
        validate_url("http://internal.example.com/path")

    assert exc.value.reason == "ssrf_private_ip"


@pytest.mark.unit
@pytest.mark.parametrize("public_ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_validate_url_public_ip_passes(
    monkeypatch: pytest.MonkeyPatch, public_ip: str
) -> None:
    _stub_resolution(monkeypatch, public_ip)

    # No exception == accepted.
    validate_url("https://example.com")


@pytest.mark.unit
def test_validate_url_rejects_if_any_resolved_ip_is_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DNS rebinding shape: one public + one private address. Must fail closed.
    _stub_resolution(monkeypatch, "8.8.8.8", "10.0.0.1")

    with pytest.raises(SecurityPolicyViolationError):
        validate_url("https://example.com")


@pytest.mark.unit
@pytest.mark.parametrize("bad_url", ["not-a-url", "/just/a/path", "http://", ""])
def test_validate_url_without_hostname_raises_invalid_url(bad_url: str) -> None:
    with pytest.raises(InvalidURLError):
        validate_url(bad_url)


@pytest.mark.unit
def test_validate_url_unresolvable_hostname_raises_invalid_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(host: str, port: object, *a: object, **k: object) -> list[tuple]:
        raise socket.gaierror("name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", _raise)

    with pytest.raises(InvalidURLError):
        validate_url("http://nonexistent.invalid")
