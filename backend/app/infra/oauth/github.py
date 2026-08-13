from __future__ import annotations

from urllib.parse import urlencode

import httpx
import structlog

from app.infra.oauth.base import OAuthProfile
from app.infra.oauth.exceptions import OAuthProviderError

logger = structlog.get_logger()

_PROVIDER = "github"
_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
_TOKEN_URL = "https://github.com/login/oauth/access_token"
_PROFILE_URL = "https://api.github.com/user"
_EMAILS_URL = "https://api.github.com/user/emails"
_SCOPE = "user:email"


class GitHubOAuthProvider:
    """GitHub — OAuth App code flow, не OIDC.

    PKCE у GitHub OAuth Apps — no-op: `code_challenge`/`code_verifier`
    передаются в теле обмена кода как и у остальных провайдеров (единый
    интерфейс не разветвляется), но GitHub их молча игнорирует — защиту
    ветки от CSRF держит сверка `state` из cookie `oauth_flow`, та же, что
    у остальных провайдеров (design-brief.md § Провайдер-слой, plan.md
    § T1.9, Open Questions № 3).

    Профиль — `GET /user`; если `email` в ответе `null` (пользователь скрыл
    его в настройках), добирается через отдельный `GET /user/emails`
    (требует scope `user:email`) — выбирается primary+verified адрес, при
    его отсутствии профиль остаётся с `email = None` без ошибки
    (research-provider-libs.md § подводные камни GitHub). Структурно
    реализует ``app.infra.oauth.base.OAuthProvider`` (Protocol —
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
        # GitHub отдаёт form-urlencoded тело по умолчанию; Accept: application/json
        # переключает ответ на JSON — иначе payload.json() ниже упадёт на парсинге.
        headers = {"Accept": "application/json"}
        try:
            response = await self._http.post(_TOKEN_URL, data=data, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "github token exchange failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            raise OAuthProviderError(_PROVIDER, "token exchange failed") from e
        except (httpx.HTTPError, OSError) as e:
            logger.warning("github token exchange request error", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "token exchange request error") from e

        try:
            payload = response.json()
            # GitHub возвращает 200 даже на невалидный code/redirect_uri, ошибка
            # приходит в теле как {"error": "...", "error_description": "..."}.
            if "error" in payload:
                raise TypeError(f"provider returned error: {payload['error']}")
            access_token = payload["access_token"]
            if not isinstance(access_token, str) or not access_token:
                raise TypeError("access_token must be a non-empty string")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("github token exchange malformed response", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "malformed token response") from e

        return access_token

    async def fetch_profile(self, *, token: str) -> OAuthProfile:
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = await self._http.get(_PROFILE_URL, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "github profile fetch failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            raise OAuthProviderError(_PROVIDER, "profile fetch failed") from e
        except (httpx.HTTPError, OSError) as e:
            logger.warning("github profile fetch request error", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "profile fetch request error") from e

        try:
            payload = response.json()
            account_id = payload["id"]
            if not isinstance(account_id, int):
                raise TypeError("id must be an integer")
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("github profile fetch malformed response", exc_info=True)
            raise OAuthProviderError(_PROVIDER, "malformed profile response") from e

        email = payload.get("email")
        email = email if isinstance(email, str) else None
        if email is None:
            email = await self._fetch_primary_email(token)

        display_name = payload.get("login")
        return OAuthProfile(
            provider=_PROVIDER,
            provider_account_id=str(account_id),
            email=email,
            display_name=display_name if isinstance(display_name, str) else None,
        )

    async def _fetch_primary_email(self, token: str) -> str | None:
        """Добор email через `/user/emails`, когда `/user` его скрывает.

        Требует scope `user:email` (запрошен в `authorize_url`). Возвращает
        primary+verified адрес, либо любой verified, либо `None` — деградация
        мягкая: отсутствующий email не блокирует вход (research-provider-libs.md).
        """
        headers = {"Authorization": f"Bearer {token}"}
        try:
            response = await self._http.get(_EMAILS_URL, headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning(
                "github emails fetch failed",
                status_code=e.response.status_code,
                exc_info=True,
            )
            return None
        except (httpx.HTTPError, OSError):
            logger.warning("github emails fetch request error", exc_info=True)
            return None

        try:
            emails = response.json()
            if not isinstance(emails, list):
                raise TypeError("emails payload must be a list")
        except (TypeError, ValueError):
            logger.warning("github emails fetch malformed response", exc_info=True)
            return None

        verified_emails = [
            entry
            for entry in emails
            if isinstance(entry, dict)
            and isinstance(entry.get("email"), str)
            and entry.get("verified") is True
        ]
        for entry in verified_emails:
            if entry.get("primary") is True:
                return str(entry["email"])
        if verified_emails:
            return str(verified_emails[0]["email"])
        return None
