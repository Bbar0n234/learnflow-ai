"""Thin helpers for driving the real auth flow over HTTP.

Pure functions, not fixtures — imported by the auth test modules. They keep the
cookie handling explicit so refresh-rotation/replay tests stay deterministic
(httpx auto-stores the rotated cookie; replay needs the *old* raw value).
"""

from __future__ import annotations

from httpx import AsyncClient, Response

DEFAULT_NAME = "alice"
DEFAULT_PASSWORD = "password123"


async def register(
    client: AsyncClient,
    name: str = DEFAULT_NAME,
    password: str = DEFAULT_PASSWORD,
) -> Response:
    return await client.post(
        "/api/auth/register", json={"name": name, "password": password}
    )


async def login(
    client: AsyncClient,
    name: str = DEFAULT_NAME,
    password: str = DEFAULT_PASSWORD,
) -> Response:
    return await client.post(
        "/api/auth/login", json={"name": name, "password": password}
    )


async def do_refresh(client: AsyncClient, token: str) -> Response:
    """Refresh with an explicit raw token, ignoring any cookie in the jar.

    The jar is cleared first so exactly one ``refresh_token`` is sent — letting
    a test replay a superseded token without the rotated one leaking in.
    """
    client.cookies.clear()
    return await client.post("/api/auth/refresh", cookies={"refresh_token": token})


def refresh_value(response: Response) -> str | None:
    """Raw refresh token set by a response, or ``None`` if none/deleted."""
    return response.cookies.get("refresh_token")
