from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.services.exceptions import InvalidURLError, SecurityPolicyViolationError

logger = structlog.get_logger()

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),  # "this host"; 0.0.0.0 → localhost on Linux
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT (RFC 6598)
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


# MCP transport defaults (mirror mcp.shared._httpx_utils.create_mcp_http_client),
# but with redirects disabled — see ``mcp_no_redirect_client_factory``.
_MCP_DEFAULT_TIMEOUT = 30.0
_MCP_DEFAULT_SSE_READ_TIMEOUT = 300.0


def mcp_no_redirect_client_factory(
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | None = None,
    auth: httpx.Auth | None = None,
) -> httpx.AsyncClient:
    """httpx client factory for MCP connections with redirects disabled.

    SSRF defense-in-depth against the validate→connect TOCTOU window:
    ``validate_url`` pins the *initial* host as public, but the MCP transport
    opens its own connection afterwards and the default MCP client follows 3xx
    redirects. A public host could redirect to a private IP after validation.
    Disabling redirects closes that bypass. (Full DNS-rebinding protection —
    pinning the resolved IP for the actual connect — is out of scope here.)
    """
    kwargs: dict[str, Any] = {"follow_redirects": False}
    if timeout is None:
        kwargs["timeout"] = httpx.Timeout(
            _MCP_DEFAULT_TIMEOUT, read=_MCP_DEFAULT_SSE_READ_TIMEOUT
        )
    else:
        kwargs["timeout"] = timeout
    if headers is not None:
        kwargs["headers"] = headers
    if auth is not None:
        kwargs["auth"] = auth
    return httpx.AsyncClient(**kwargs)


def validate_url(url: str) -> None:
    """Validate that the URL is not pointing to private/internal IPs (SSRF protection).

    Raises:
        InvalidURLError (400): URL is syntactically invalid or hostname cannot be
            resolved (DNS failure — client supplied a bad hostname).
        SecurityPolicyViolationError (422): hostname resolves to a private/internal
            IP (SSRF attempt).
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise InvalidURLError(f"Невалидный URL — нет hostname: {url!r}")

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise InvalidURLError(f"Не удалось найти хост {hostname!r}") from e

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        ip = ipaddress.ip_address(ip_str)
        # Normalize IPv4-mapped IPv6 (e.g. ::ffff:10.0.0.1) to the embedded
        # IPv4 so private ranges can't be smuggled through the v6 form.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        for network in _PRIVATE_NETWORKS:
            if ip in network:
                logger.error("ssrf validation failed", url=url, resolved_ip=ip_str)
                raise SecurityPolicyViolationError(
                    reason="ssrf_private_ip",
                    detail="URL указывает на приватный или внутренний адрес",
                )
