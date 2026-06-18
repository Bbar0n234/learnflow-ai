from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import structlog

from app.services.exceptions import InvalidURLError, SecurityPolicyViolationError

logger = structlog.get_logger()

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


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
        raise InvalidURLError(f"Invalid URL: no hostname in {url!r}")

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        raise InvalidURLError(f"Cannot resolve hostname: {hostname!r}") from e

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        ip = ipaddress.ip_address(ip_str)
        for network in _PRIVATE_NETWORKS:
            if ip in network:
                logger.error("ssrf validation failed", url=url, resolved_ip=ip_str)
                raise SecurityPolicyViolationError(
                    reason="ssrf_private_ip",
                    detail="URL resolves to a private or internal address",
                )
