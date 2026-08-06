"""Env surface of the client-IP knobs: safe defaults, fail-fast on nonsense.

The two settings encode a trust decision, so a typo must stop the process at
boot rather than silently pick a mode nobody intended: an unknown source and a
non-positive hop count are rejected by the type, not discovered at runtime.
"""

from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import ValidationError

_CLIENT_IP_ENV = ("CLIENT_IP_SOURCE", "CLIENT_IP_XFF_HOPS")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No ambient client-IP variables (the Makefile sources .env before pytest)."""
    for name in _CLIENT_IP_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.unit
def test_defaults_are_socket_and_a_single_hop(clean_env: pytest.MonkeyPatch) -> None:
    settings = Settings()

    assert settings.client_ip_source == "socket"
    assert settings.client_ip_xff_hops == 1


@pytest.mark.unit
@pytest.mark.parametrize("source", ["socket", "x-real-ip", "x-forwarded-for"])
def test_documented_sources_are_accepted(
    clean_env: pytest.MonkeyPatch, source: str
) -> None:
    clean_env.setenv("CLIENT_IP_SOURCE", source)

    assert Settings().client_ip_source == source


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CLIENT_IP_SOURCE", "x-forwarded"),
        ("CLIENT_IP_SOURCE", "true"),
        ("CLIENT_IP_XFF_HOPS", "0"),
        ("CLIENT_IP_XFF_HOPS", "-1"),
    ],
)
def test_invalid_values_are_rejected_at_construction(
    clean_env: pytest.MonkeyPatch, name: str, value: str
) -> None:
    clean_env.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings()
