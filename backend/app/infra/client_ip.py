from __future__ import annotations

import structlog
from fastapi import Request

from app.config import Settings

logger = structlog.get_logger()

_HEALTH_PATH = "/health"


def is_health_path(path: str) -> bool:
    """True для пути health-чека — единственное место, где записан `/health`.

    Health-путь исключается из fallback-предупреждений и не биндит `ip` в
    contextvars: docker healthcheck идёт мимо nginx и proxy-заголовков там
    никогда нет, поэтому WARNING на нём — не сигнал дрейфа, а шум (~8-9 тыс.
    в сутки).
    """
    return path == _HEALTH_PATH


def _socket_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _fallback_to_socket(request: Request, settings: Settings, reason: str) -> str:
    if not is_health_path(request.url.path):
        logger.warning(
            "client ip fallback to socket",
            client_ip_source=settings.client_ip_source,
            reason=reason,
            path=request.url.path,
        )
    return _socket_ip(request)


def get_client_ip(request: Request, settings: Settings) -> str:
    """Единая точка чтения клиентского IP.

    Источник определяется `settings.client_ip_source` — код на месте вызова
    не решает, какому заголовку доверять. `X-Real-IP` и `X-Forwarded-For`
    нигде за пределами этого модуля не читаются (grep-инвариант,
    doc/tech/conventions.md § Logging Conventions).
    """
    if settings.client_ip_source == "socket":
        return _socket_ip(request)

    if settings.client_ip_source == "x-real-ip":
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and real_ip.strip():
            return real_ip.strip()
        return _fallback_to_socket(request, settings, "x-real-ip header missing")

    # x-forwarded-for
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        hops = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(hops) >= settings.client_ip_xff_hops:
            return hops[-settings.client_ip_xff_hops]
    return _fallback_to_socket(request, settings, "x-forwarded-for header insufficient")
