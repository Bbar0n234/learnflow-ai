from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Response

from app.config import Settings

COOKIE_NAME = "oauth_flow"
_COOKIE_PATH = "/api/auth/oauth"
_MAX_AGE_SECONDS = 600
_ALGORITHM = "HS256"


@dataclass(frozen=True)
class OAuthFlowState:
    """Decoded claims of the ``oauth_flow`` cookie for one authorize→callback
    round-trip (design-brief.md § Хранение state)."""

    state: str
    verifier: str
    provider: str
    next: str


def is_safe_next_path(path: str) -> bool:
    """Относительный путь — начинается с ``/``, не с ``//`` (не open redirect)."""
    return path.startswith("/") and not path.startswith("//")


def encode_flow_cookie(
    *,
    state: str,
    verifier: str,
    provider: str,
    next_path: str,
    jwt_secret: str,
) -> str:
    """Подписанные ``JWT_SECRET`` claims для cookie ``oauth_flow``: ``state``/
    ``verifier`` (PKCE), ``provider`` (сверяется на декоде — cookie не годится
    для другого провайдера), ``next`` (уже провалидированный вызывающим),
    ``exp: +10 мин``.
    """
    payload = {
        "state": state,
        "verifier": verifier,
        "provider": provider,
        "next": next_path,
        "exp": datetime.now(UTC) + timedelta(seconds=_MAX_AGE_SECONDS),
    }
    return jwt.encode(payload, jwt_secret, algorithm=_ALGORITHM)


def decode_flow_cookie(
    token: str, *, provider: str, jwt_secret: str
) -> OAuthFlowState | None:
    """``None`` на любой отказ — подпись, `exp`, несовпадение `provider`,
    отсутствующие/битые claims. Вызывающий (``routes/oauth.py``) сводит все
    эти причины в одну ветку ``flow_expired`` — различать их дальше незачем.
    """
    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    if payload.get("provider") != provider:
        return None
    try:
        return OAuthFlowState(
            state=payload["state"],
            verifier=payload["verifier"],
            provider=payload["provider"],
            next=payload["next"],
        )
    except KeyError:
        return None


def set_flow_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=_COOKIE_PATH,
        max_age=_MAX_AGE_SECONDS,
    )


def delete_flow_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path=_COOKIE_PATH,
    )
