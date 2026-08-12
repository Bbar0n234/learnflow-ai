"""MMDB-backed IP → country resolution for the OAuth гео-gate.

Fail-closed in the direction the law requires: any failure to resolve a
country (unset/missing database, lookup miss, unparsable IP) degrades to
``Settings.geoip_fallback_country`` (default ``RU``) — never to "no
restriction". Only ``app.infra.client_ip.get_client_ip`` is a legal IP
source (design-brief.md § Гео-gate).
"""

from __future__ import annotations

from pathlib import Path

import maxminddb
import structlog
from maxminddb.types import Record

logger = structlog.get_logger()


def open_reader(db_path: str) -> maxminddb.Reader | None:
    """Opens the MMDB reader for the process lifetime.

    Called once from lifespan and stored on ``app.state`` — no module-level
    singleton (conventions.md § Состояние на уровне модуля). Missing/unset
    path degrades to a warning and ``None``; callers of `resolve_country`
    treat ``None`` the same as any other unresolvable lookup — fallback
    country, not a blocked start.
    """
    if not db_path:
        logger.warning(
            "geoip db path not configured, all lookups fall back to "
            "GEOIP_FALLBACK_COUNTRY"
        )
        return None
    if not Path(db_path).is_file():
        logger.warning("geoip db file not found, falling back", db_path=db_path)
        return None
    try:
        return maxminddb.open_database(db_path)
    except Exception:
        logger.warning(
            "geoip db failed to open, falling back", db_path=db_path, exc_info=True
        )
        return None


def _extract_country_code(record: Record | None) -> str | None:
    """Extracts an ISO country code from an MMDB record.

    ``Record`` is a recursive union (``str | bool | float | int | list |
    dict``) — navigation is by explicit ``isinstance`` checks, no attribute
    access. Compatible with both the flat IPinfo Lite schema
    (``country_code``) and the nested GeoLite2 schema (``country.iso_code``).
    """
    if not isinstance(record, dict):
        return None

    flat = record.get("country_code")
    if isinstance(flat, str) and flat:
        return flat.upper()

    nested = record.get("country")
    if isinstance(nested, dict):
        iso = nested.get("iso_code")
        if isinstance(iso, str) and iso:
            return iso.upper()

    return None


def resolve_country(
    reader: maxminddb.Reader | None, ip: str, fallback_country: str
) -> str:
    """Resolves the caller's country from ``ip``, degrading to
    ``fallback_country`` when the database is unavailable, the lookup
    misses (private/dev addresses), or ``ip`` is unparsable — including the
    literal ``"unknown"`` that ``get_client_ip`` returns when there is no
    client at all (``Reader.get`` raises ``ValueError`` on that input).

    Always returns an upper-case ISO code: the gate compares strictly, so a
    fallback written as ``GEOIP_FALLBACK_COUNTRY=ru`` must not turn
    fail-closed inside out. Normalisation happens once, here, for every exit
    of the function — the database path is already normalised by
    `_extract_country_code`.
    """
    fallback = fallback_country.strip().upper()
    if reader is None:
        return fallback
    try:
        record = reader.get(ip)
    except ValueError:
        return fallback
    country = _extract_country_code(record)
    return country if country is not None else fallback
