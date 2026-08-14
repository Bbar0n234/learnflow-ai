from __future__ import annotations

from urllib.parse import urlencode

import httpx
import structlog

from app.infra.oauth.base import OAuthProfile
from app.infra.oauth.exceptions import OAuthProviderError

logger = structlog.get_logger()

_PROVIDER = "yandex"
_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
_TOKEN_URL = "https://oauth.yandex.ru/token"
_PROFILE_URL = "https://login.yandex.ru/info"


class YandexOAuthProvider:
    """Яндекс ID — обычный OAuth 2.0 Authorization Code, не OIDC.

    Профиль отдаётся отдельным HTTP-запросом (``login.yandex.ru/info``), не
    ``id_token`` — JWKS/подпись здесь не нужны
    (research-provider-libs.md § Яндекс ID). Структурно реализует
    ``app.infra.oauth.base.OAuthProvider`` (Protocol — совместимость
    проверяет mypy, явного наследования не требуется).
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = http_client

    def authorize_url(self, *, state: str, challenge: str, redirect_uri: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(
        self, *, code: str, verifier: str, redirect_uri: str
    ) -> str:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        try:
            response = await self._http.post(_TOKEN_URL, data=data)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "yandex token exchange failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            raise OAuthProviderError(_PROVIDER, "token exchange failed") from e
        except (httpx.HTTPError, OSError) as e:
            logger.warning("yandex token exchange request error", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "token exchange request error") from e

        try:
            payload = response.json()
            access_token = payload["access_token"]
            if not isinstance(access_token, str) or not access_token:
                raise TypeError("access_token must be a non-empty string")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("yandex token exchange malformed response", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "malformed token response") from e

        return access_token

    async def fetch_profile(self, *, token: str) -> OAuthProfile:
        headers = {"Authorization": f"OAuth {token}"}
        try:
            response = await self._http.get(_PROFILE_URL, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "yandex profile fetch failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            raise OAuthProviderError(_PROVIDER, "profile fetch failed") from e
        except (httpx.HTTPError, OSError) as e:
            logger.warning("yandex profile fetch request error", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "profile fetch request error") from e

        try:
            payload = response.json()
            account_id = payload["id"]
            if not isinstance(account_id, str) or not account_id:
                raise TypeError("id must be a non-empty string")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("yandex profile fetch malformed response", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "malformed profile response") from e

        email = payload.get("default_email")
        display_name = payload.get("login")
        return OAuthProfile(
            provider=_PROVIDER,
            provider_account_id=account_id,
            email=email if isinstance(email, str) else None,
            display_name=display_name if isinstance(display_name, str) else None,
        )
