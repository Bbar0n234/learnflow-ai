from __future__ import annotations

import httpx

from app.config import Settings
from app.infra.oauth.base import OAuthProfile, OAuthProvider
from app.infra.oauth.github import GitHubOAuthProvider
from app.infra.oauth.google import GoogleOAuthProvider
from app.infra.oauth.yandex import YandexOAuthProvider

__all__ = ["OAuthProfile", "OAuthProvider", "build_oauth_registry"]


def build_oauth_registry(
    settings: Settings, http_client: httpx.AsyncClient
) -> dict[str, OAuthProvider]:
    """Собирает реестр активных провайдеров: активен ⇔ заданы обе креды.

    Фабрика — вызывается один раз из ``lifespan``, реестр живёт в
    ``app.state`` (никакого module-level state, conventions.md § Module-level
    state).
    """
    registry: dict[str, OAuthProvider] = {}

    if settings.oauth_yandex_client_id and settings.oauth_yandex_client_secret:
        registry["yandex"] = YandexOAuthProvider(
            client_id=settings.oauth_yandex_client_id,
            client_secret=settings.oauth_yandex_client_secret,
            http_client=http_client,
        )

    if settings.oauth_google_client_id and settings.oauth_google_client_secret:
        registry["google"] = GoogleOAuthProvider(
            client_id=settings.oauth_google_client_id,
            client_secret=settings.oauth_google_client_secret,
            http_client=http_client,
        )

    if settings.oauth_github_client_id and settings.oauth_github_client_secret:
        registry["github"] = GitHubOAuthProvider(
            client_id=settings.oauth_github_client_id,
            client_secret=settings.oauth_github_client_secret,
            http_client=http_client,
        )

    return registry
