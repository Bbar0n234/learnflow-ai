from __future__ import annotations

from urllib.parse import urlencode

import httpx
import structlog

from app.infra.oauth.base import OAuthProfile
from app.infra.oauth.exceptions import OAuthProviderError

logger = structlog.get_logger()

_PROVIDER = "google"
_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_PROFILE_URL = "https://openidconnect.googleapis.com/v1/userinfo"
_SCOPE = "openid email profile"


class GoogleOAuthProvider:
    """Google — OIDC-совместимый Authorization Code flow.

    Профиль берётся через userinfo-endpoint по access token, не из
    ``id_token`` — JWKS-валидация ``id_token`` не требуется и не делается
    (design-brief.md § Провайдер-слой, research-provider-libs.md § Google).
    Структурно реализует ``app.infra.oauth.base.OAuthProvider`` (Protocol —
    совместимость проверяет mypy, явного наследования не требуется).
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
            "scope": _SCOPE,
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
                "google token exchange failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            raise OAuthProviderError(_PROVIDER, "token exchange failed") from e
        except (httpx.HTTPError, OSError) as e:
            logger.warning("google token exchange request error", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "token exchange request error") from e

        try:
            payload = response.json()
            access_token = payload["access_token"]
            if not isinstance(access_token, str) or not access_token:
                raise TypeError("access_token must be a non-empty string")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("google token exchange malformed response", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "malformed token response") from e

        return access_token

    async def fetch_profile(self, *, token: str) -> OAuthProfile:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = await self._http.get(_PROFILE_URL, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "google profile fetch failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            raise OAuthProviderError(_PROVIDER, "profile fetch failed") from e
        except (httpx.HTTPError, OSError) as e:
            logger.warning("google profile fetch request error", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "profile fetch request error") from e

        try:
            payload = response.json()
            account_id = payload["sub"]
            if not isinstance(account_id, str) or not account_id:
                raise TypeError("sub must be a non-empty string")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("google profile fetch malformed response", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "malformed profile response") from e

        email = payload.get("email")
        display_name = payload.get("given_name")
        return OAuthProfile(
            provider=_PROVIDER,
            provider_account_id=account_id,
            email=email if isinstance(email, str) else None,
            display_name=display_name if isinstance(display_name, str) else None,
        )
