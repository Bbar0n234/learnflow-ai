"""The request middleware: which address downstream code gets to log.

Everything logged during a request inherits ``ip`` from structlog contextvars,
so this is where a spoofed header would end up poisoning logs and SIEM events.
The tests drive a real app over an in-memory ASGI client whose TCP peer is
known, configure the source through the environment (as a real boot does) and
read back what the middleware bound.

Most cases run against a probe route and need no database; the security-event
case goes through a real auth route, which resolves a DB session as a
dependency, so the transactional session is wired in there.
"""

from __future__ import annotations

import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from tests.client_ip._helpers import (
    CLIENT_SPOOF_IP,
    PROBE_PATH,
    PROXY_APPENDED_IP,
    SOCKET_IP,
    asgi_client,
    build_app,
)

SPOOFED_HEADERS = {
    "X-Forwarded-For": CLIENT_SPOOF_IP,
    "X-Real-IP": CLIENT_SPOOF_IP,
}

#: Event name of the fallback warning — the observable contract of *this*
#: subsystem, unlike the wording of any other component's log lines.
FALLBACK_WARNING = "client ip fallback to socket"


@pytest.mark.integration
async def test_socket_mode_binds_the_connection_address_not_the_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_app(monkeypatch, source="socket")

    async with asgi_client(app) as client:
        context = (await client.get(PROBE_PATH, headers=SPOOFED_HEADERS)).json()

    assert context["ip"] == SOCKET_IP


@pytest.mark.integration
async def test_x_real_ip_mode_binds_the_proxy_supplied_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_app(monkeypatch, source="x-real-ip")

    async with asgi_client(app) as client:
        context = (
            await client.get(
                PROBE_PATH,
                headers={
                    "X-Real-IP": PROXY_APPENDED_IP,
                    "X-Forwarded-For": CLIENT_SPOOF_IP,
                },
            )
        ).json()

    assert context["ip"] == PROXY_APPENDED_IP


@pytest.mark.integration
async def test_x_forwarded_for_mode_honours_the_configured_hop_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_app(monkeypatch, source="x-forwarded-for", hops=2)

    async with asgi_client(app) as client:
        context = (
            await client.get(
                PROBE_PATH,
                headers={
                    "X-Forwarded-For": (
                        f"{CLIENT_SPOOF_IP}, {PROXY_APPENDED_IP}, 192.0.2.20"
                    )
                },
            )
        ).json()

    assert context["ip"] == PROXY_APPENDED_IP


@pytest.mark.integration
async def test_missing_configured_header_falls_back_and_warns_on_a_normal_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_app(monkeypatch, source="x-real-ip")

    async with asgi_client(app) as client:
        with capture_logs() as logs:
            context = (await client.get(PROBE_PATH)).json()

    assert context["ip"] == SOCKET_IP
    assert [entry["event"] for entry in logs if entry["log_level"] == "warning"] == [
        FALLBACK_WARNING
    ]


@pytest.mark.integration
async def test_health_requests_bind_no_ip_and_stay_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The docker healthcheck hits /health every 10s bypassing nginx, so a
    # fallback warning there would be pure noise — and no client address is
    # needed to answer it.
    app = build_app(monkeypatch, source="x-real-ip")

    async with asgi_client(app) as client:
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            response = await client.get("/health")

    assert response.status_code == 503  # engine stub reports the DB as down
    # Asserted structurally, not by the wording of the health handler's own
    # message: that line belongs to another subsystem and may be reworded
    # without touching the client-IP contract.
    assert logs, "the health request must leave at least one record to inspect"
    assert all(entry["event"] != FALLBACK_WARNING for entry in logs)
    assert all("ip" not in entry for entry in logs)  # no client address bound...
    assert any("request_id" in entry for entry in logs)  # ...rest of context is


@pytest.mark.integration
async def test_security_events_carry_the_trusted_address(
    monkeypatch: pytest.MonkeyPatch, db_session: AsyncSession
) -> None:
    # Counterpart of the health case: on any other path the address reaches the
    # log record — this is the field SIEM events are built from, so it must
    # show the proxy-supplied value and not what the client wrote.
    app = build_app(monkeypatch, source="x-real-ip", session=db_session)
    headers = {"X-Real-IP": PROXY_APPENDED_IP, "X-Forwarded-For": CLIENT_SPOOF_IP}

    async with asgi_client(app) as client:
        for _ in range(10):  # cookieless refresh: 401 each
            await client.post("/api/auth/refresh", headers=headers)
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            response = await client.post("/api/auth/refresh", headers=headers)

    assert response.status_code == 429
    (event,) = [entry for entry in logs if entry.get("security_event")]
    assert event["ip"] == PROXY_APPENDED_IP
