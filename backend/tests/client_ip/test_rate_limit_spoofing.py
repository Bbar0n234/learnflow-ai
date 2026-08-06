"""Per-IP rate limits keyed on the *resolved* address.

This is the attack the track closes: the auth budgets are keyed on the client
IP (``register:{ip}``, ``login:{name}:{ip}``, ``refresh:{ip}``), so if a client
could pick that value by sending a header, it could mint a fresh budget per
request and walk around the limit. Each test drives one client socket through
the real routes and watches whose budget gets spent — all three routes that
read an address are exercised, in the modes a deployment can be in.

All routes here resolve a DB session as a dependency, so the real transactional
session is wired in even where the request never reaches a query (a cookieless
refresh is refused before any lookup).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.client_ip._helpers import (
    PROXY_APPENDED_IP,
    asgi_client,
    build_app,
)

PASSWORD = "password123"


async def _register(client: AsyncClient, name: str, headers: dict[str, str]) -> int:
    response = await client.post(
        "/api/auth/register",
        json={"name": name, "password": PASSWORD},
        headers=headers,
    )
    return response.status_code


@pytest.mark.integration
async def test_spoofed_headers_do_not_split_the_register_budget(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    # Registration allows 3 per hour per IP. In socket mode the headers below
    # are ignored, so all four attempts share one budget and the fourth is
    # refused — under the old leftmost-XFF reading each attempt looked like a
    # different client and all four would have passed.
    app = build_app(monkeypatch, source="socket", session=db_session)

    async with asgi_client(app) as client:
        statuses = [
            await _register(
                client,
                f"spoofer-{index}",
                {"X-Forwarded-For": f"203.0.113.{index}", "X-Real-IP": "203.0.113.9"},
            )
            for index in range(4)
        ]

    assert statuses == [200, 200, 200, 429]


@pytest.mark.integration
async def test_forwarded_for_prefix_does_not_split_the_register_budget(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    # Same attempt against the x-forwarded-for mode: the client varies the part
    # of the chain it controls (everything left of the proxy-appended entry),
    # while the hop the proxy wrote stays the same — one budget, still refused.
    app = build_app(monkeypatch, source="x-forwarded-for", hops=1, session=db_session)

    async with asgi_client(app) as client:
        statuses = [
            await _register(
                client,
                f"chainer-{index}",
                {"X-Forwarded-For": f"203.0.113.{index}, {PROXY_APPENDED_IP}"},
            )
            for index in range(4)
        ]

    assert statuses == [200, 200, 200, 429]


@pytest.mark.integration
async def test_spoofed_forwarded_for_does_not_split_the_register_budget_in_prod_mode(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    # The mode production actually runs in: nginx replaces X-Real-IP wholesale,
    # so the client's own X-Forwarded-For must count for nothing — one budget
    # per real client, however the client decorates the request.
    app = build_app(monkeypatch, source="x-real-ip", session=db_session)

    async with asgi_client(app) as client:
        statuses = [
            await _register(
                client,
                f"masquerader-{index}",
                {
                    "X-Real-IP": PROXY_APPENDED_IP,
                    "X-Forwarded-For": f"203.0.113.{index}, 198.51.100.{index}",
                },
            )
            for index in range(4)
        ]

    assert statuses == [200, 200, 200, 429]


@pytest.mark.integration
async def test_spoofed_headers_do_not_split_the_login_budget(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    # The third reader of the address: login keys on name *and* IP, 5 per
    # minute. Failed credentials still burn the budget, so six attempts under
    # one name with a header changing every time must end in 429 — a naive
    # header read would hand each attempt its own budget.
    app = build_app(monkeypatch, source="socket", session=db_session)

    async with asgi_client(app) as client:
        statuses = [
            (
                await client.post(
                    "/api/auth/login",
                    json={"name": "victim", "password": PASSWORD},
                    headers={
                        "X-Forwarded-For": f"203.0.113.{index}",
                        "X-Real-IP": f"203.0.113.{index}",
                    },
                )
            ).status_code
            for index in range(6)
        ]

    assert statuses == [401] * 5 + [429]


@pytest.mark.integration
async def test_distinct_trusted_addresses_get_independent_budgets(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    # The positive control: when the source really is trustworthy, two clients
    # behind the same proxy must not share a budget — otherwise the fix would
    # trade a bypass for a denial of service. Refresh allows 10 per minute per
    # IP and answers cookieless calls with 401.
    app = build_app(monkeypatch, source="x-real-ip", session=db_session)

    async with asgi_client(app) as client:
        noisy = [
            (
                await client.post(
                    "/api/auth/refresh", headers={"X-Real-IP": PROXY_APPENDED_IP}
                )
            ).status_code
            for _ in range(11)
        ]
        neighbour = await client.post(
            "/api/auth/refresh", headers={"X-Real-IP": "192.0.2.55"}
        )

    assert noisy == [401] * 10 + [429]
    assert neighbour.status_code == 401
