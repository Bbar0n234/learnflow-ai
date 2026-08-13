from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OAuthProfile:
    """Normalized profile returned by a provider after a successful exchange.

    Internal value object (conventions.md § Типизация — `@dataclass` frozen):
    not sourced from an external boundary directly — each provider's
    ``fetch_profile`` maps its own payload into this shape before returning it,
    so no Pydantic validation is needed here.
    """

    provider: str
    provider_account_id: str
    email: str | None
    display_name: str | None


class OAuthProvider(Protocol):
    """Point of variability across OAuth providers (conventions.md § Интерфейсы).

    Implementations (``yandex.py``, ``google.py``, ``github.py``) hold their
    own ``client_id``/``client_secret`` (sourced from ``Settings``
    at registry build time) and a reference to the shared
    ``httpx.AsyncClient`` — no module-level state, no per-request client
    construction (design-brief.md § Провайдер-слой). Instances are assembled
    into a registry by ``app.infra.oauth.build_oauth_registry`` and live in
    ``app.state``, wired from ``lifespan``.
    """

    def authorize_url(self, *, state: str, challenge: str, redirect_uri: str) -> str:
        """Build the provider's authorization URL (PKCE S256 + state)."""
        ...

    async def exchange_code(
        self, *, code: str, verifier: str, redirect_uri: str
    ) -> str:
        """Exchange the authorization code for an access token.

        Raises:
            OAuthProviderError: non-2xx response, timeout, or malformed body.
        """
        ...

    async def fetch_profile(self, *, token: str) -> OAuthProfile:
        """Fetch and normalize the user's profile using the access token.

        Raises:
            OAuthProviderError: non-2xx response, timeout, or malformed body.
        """
        ...
