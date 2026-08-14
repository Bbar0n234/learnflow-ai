from __future__ import annotations

from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from siem_contracts import (
    AUTH_OAUTH_FAILED,
    AUTH_OAUTH_SUCCESS,
    RATE_LIMIT_OAUTH_EXCEEDED,
)

from app.api.cookies import set_refresh_cookie
from app.api.deps import DBSession, SettingsDep
from app.api.schemas.oauth import ProvidersResponse
from app.config import Settings
from app.infra.client_ip import get_client_ip
from app.infra.geoip import resolve_country
from app.infra.oauth import flow_state
from app.infra.oauth.base import OAuthProvider
from app.infra.oauth.exceptions import OAuthProviderError
from app.infra.oauth.flow_state import (
    decode_flow_cookie,
    delete_flow_cookie,
    encode_flow_cookie,
    is_safe_next_path,
    set_flow_cookie,
)
from app.infra.oauth.pkce import (
    derive_code_challenge,
    generate_code_verifier,
    generate_state,
)
from app.infra.rate_limit import RateLimiter
from app.services.exceptions import OAuthAccountCreationError
from app.services.oauth import OAuthService

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["oauth"])

_RATE_LIMIT_MAX_REQUESTS = 10
_RATE_LIMIT_WINDOW_SECONDS = 60
_DEFAULT_NEXT_PATH = "/"
_LOGIN_PATH = "/login"

# Гео-gate: бизнес-инвариант «разрешённые для RU провайдеры» — константа в
# коде, не env (design-brief.md § Конфигурация). Любая другая страна не
# ограничена — все активные провайдеры доступны.
_GEO_RESTRICTED_COUNTRY = "RU"
_GEO_ALLOWED_PROVIDERS_RU = frozenset({"yandex"})

# Закрытый реестр кодов `/login?error=` (design-brief.md § Эндпоинты, таблица
# кодов) — совпадает буквально с фронтендовым union в `LoginPage.tsx`.
OAuthErrorCode = Literal[
    "access_denied",
    "flow_expired",
    "provider_not_available_in_region",
    "provider_unavailable",
    "oauth_failed",
]


def _get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


RateLimiterDep = Annotated[RateLimiter, Depends(_get_rate_limiter)]

FlowCookie = Annotated[str | None, Cookie(alias=flow_state.COOKIE_NAME)]
NextQuery = Annotated[str, Query(alias="next")]


def _resolve_provider(request: Request, provider: str) -> OAuthProvider:
    """``{provider}`` валидируется по реестру активных на ОБОИХ эндпоинтах,
    до всех остальных веток (design-brief.md § Эндпоинты, утверждение под
    таблицей) — неизвестный/выключенный провайдер даёт 404, не редирект.
    """
    registry: dict[str, OAuthProvider] = request.app.state.oauth_providers
    impl = registry.get(provider)
    if impl is None:
        raise HTTPException(
            status_code=404, detail="Провайдер входа не найден или отключён"
        )
    return impl


def _check_oauth_rate_limit(rate_limiter: RateLimiter, key: str) -> None:
    """10/мин/IP, раздельные ключи ``oauth_authorize:{ip}``/``oauth_callback:{ip}``
    (design-brief.md § Эндпоинты — бюджет на каждый эндпоинт отдельно, не общий).
    """
    allowed, retry_after = rate_limiter.is_allowed(
        key, _RATE_LIMIT_MAX_REQUESTS, _RATE_LIMIT_WINDOW_SECONDS
    )
    if not allowed:
        logger.warning(
            "oauth rate limit exceeded",
            security_event=True,
            event_type=RATE_LIMIT_OAUTH_EXCEEDED,
            severity="warning",
            metadata={
                "key": key,
                "limit": _RATE_LIMIT_MAX_REQUESTS,
                "window": _RATE_LIMIT_WINDOW_SECONDS,
            },
        )
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов, попробуйте позже",
            headers={"Retry-After": str(retry_after)},
        )


def _redirect_uri(settings: Settings, provider: str) -> str:
    """Строго ``{OAUTH_REDIRECT_BASE_URL}/api/auth/oauth/{provider}/callback`` —
    одинаково в authorize и в обмене кода на callback'е (провайдеры сверяют
    совпадение); host не подменяется ни из ``Request.url``, ни из заголовков.
    """
    return f"{settings.oauth_redirect_base_url}/api/auth/oauth/{provider}/callback"


def _login_redirect(
    error_code: OAuthErrorCode, *, delete_cookie: bool, settings: Settings
) -> RedirectResponse:
    """Редирект на ``/login?error=<код>`` из закрытого реестра. Cookie
    ``oauth_flow`` гасится на каждой терминальной ветке, кроме «cookie
    отсутствует» — вызывающий передаёт это через ``delete_cookie``.
    """
    response = RedirectResponse(
        url=f"{_LOGIN_PATH}?error={error_code}", status_code=302
    )
    if delete_cookie:
        delete_flow_cookie(response, settings)
    return response


def _emit_oauth_failed(provider: str, reason: str) -> None:
    logger.warning(
        "oauth login failed",
        security_event=True,
        event_type=AUTH_OAUTH_FAILED,
        severity="warning",
        metadata={"provider": provider, "reason": reason},
    )


def _emit_oauth_success(provider: str, new_user: bool) -> None:
    logger.info(
        "oauth login success",
        security_event=True,
        event_type=AUTH_OAUTH_SUCCESS,
        severity="info",
        metadata={"provider": provider, "new_user": new_user},
    )


def _is_provider_allowed_for_country(provider: str, country: str) -> bool:
    """RU → только `_GEO_ALLOWED_PROVIDERS_RU`; любая другая страна не
    ограничена (design-brief.md § Гео-gate).
    """
    if country != _GEO_RESTRICTED_COUNTRY:
        return True
    return provider in _GEO_ALLOWED_PROVIDERS_RU


def _resolve_client_country(request: Request, settings: Settings, ip: str) -> str:
    reader = request.app.state.geoip_reader
    return resolve_country(reader, ip, settings.geoip_fallback_country)


def _emit_geo_denied(provider: str, country: str) -> None:
    """Гео-отказ — штатная политика показа, не security-событие
    (design-brief.md § Эндпоинты, маппинг веток callback'а): structlog-инфо,
    без SIEM.
    """
    logger.info(
        "oauth provider not available in region",
        provider=provider,
        country=country,
    )


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers(request: Request, settings: SettingsDep) -> ProvidersResponse:
    """Состав — активные провайдеры реестра, отфильтрованные гео-gate'ом:
    RU → `{yandex} ∩ активные` (при незаполненных кредах Яндекса RU-
    пользователь получает только пароль, кнопки в 404 быть не должно);
    иначе — все активные провайдеры (design-brief.md § Гео-gate).
    """
    registry: dict[str, OAuthProvider] = request.app.state.oauth_providers
    ip = get_client_ip(request, settings)
    country = _resolve_client_country(request, settings, ip)
    providers = [p for p in registry if _is_provider_allowed_for_country(p, country)]
    return ProvidersResponse(providers=sorted(providers), password=True)


@router.get("/oauth/{provider}/authorize")
async def authorize(
    provider: str,
    request: Request,
    settings: SettingsDep,
    rate_limiter: RateLimiterDep,
    next_path: NextQuery = _DEFAULT_NEXT_PATH,
) -> RedirectResponse:
    provider_impl = _resolve_provider(request, provider)
    ip = get_client_ip(request, settings)
    _check_oauth_rate_limit(rate_limiter, f"oauth_authorize:{ip}")

    country = _resolve_client_country(request, settings, ip)
    if not _is_provider_allowed_for_country(provider, country):
        _emit_geo_denied(provider, country)
        return _login_redirect(
            "provider_not_available_in_region", delete_cookie=False, settings=settings
        )

    safe_next = next_path if is_safe_next_path(next_path) else _DEFAULT_NEXT_PATH

    state = generate_state()
    verifier = generate_code_verifier()
    challenge = derive_code_challenge(verifier)
    redirect_uri = _redirect_uri(settings, provider)
    authorize_url = provider_impl.authorize_url(
        state=state, challenge=challenge, redirect_uri=redirect_uri
    )

    flow_token = encode_flow_cookie(
        state=state,
        verifier=verifier,
        provider=provider,
        next_path=safe_next,
        jwt_secret=settings.jwt_secret,
    )
    response = RedirectResponse(url=authorize_url, status_code=302)
    set_flow_cookie(response, flow_token, settings)
    return response


@router.get("/oauth/{provider}/callback")
async def callback(
    provider: str,
    request: Request,
    session: DBSession,
    settings: SettingsDep,
    rate_limiter: RateLimiterDep,
    oauth_flow: FlowCookie = None,
) -> RedirectResponse:
    provider_impl = _resolve_provider(request, provider)
    ip = get_client_ip(request, settings)
    _check_oauth_rate_limit(rate_limiter, f"oauth_callback:{ip}")

    cookie_present = oauth_flow is not None

    # Ветка 1: код ошибки от провайдера — до сверки state (design-brief.md
    # § Эндпоинты, диаграмма веток callback'а). `access_denied` — штатный
    # отказ пользователя на экране провайдера, не событие; любой другой код
    # (мисконфиг клиента, отозванный secret, 5xx провайдера) — операционная
    # деградация категории `provider_unavailable`: наблюдаемый лог с кодом
    # провайдера, реестр `/login?error=` не расширяется.
    provider_error = request.query_params.get("error")
    if provider_error and provider_error != "access_denied":
        logger.warning(
            "oauth provider returned error", provider=provider, error=provider_error
        )
        return _login_redirect(
            "provider_unavailable", delete_cookie=cookie_present, settings=settings
        )
    if provider_error:
        return _login_redirect(
            "access_denied", delete_cookie=cookie_present, settings=settings
        )

    # Ветка 2: cookie/state — нет/протухла/не совпала (включая повторный
    # заход на callback — cookie уже погашена предыдущим терминальным
    # исходом).
    flow = (
        decode_flow_cookie(
            oauth_flow, provider=provider, jwt_secret=settings.jwt_secret
        )
        if oauth_flow is not None
        else None
    )
    if flow is None or request.query_params.get("state") != flow.state:
        _emit_oauth_failed(provider, "flow_expired")
        return _login_redirect(
            "flow_expired", delete_cookie=cookie_present, settings=settings
        )

    # Ветка 3 (гео-gate): проверка обязательна и здесь, не только на
    # authorize — смена IP между шагами и прямое обращение к callback мимо
    # UI (design-brief.md § Гео-gate).
    country = _resolve_client_country(request, settings, ip)
    if not _is_provider_allowed_for_country(provider, country):
        _emit_geo_denied(provider, country)
        return _login_redirect(
            "provider_not_available_in_region", delete_cookie=True, settings=settings
        )

    # Ветка 4: обмен code → токен, userinfo. Отсутствующий `code` (прямое
    # обращение к callback мимо провайдера) не отличимо от отказа обмена —
    # тот же диаграммный исход (design-brief.md: обе ветки EX-неуспеха ведут
    # в `provider_unavailable`).
    code = request.query_params.get("code")
    redirect_uri = _redirect_uri(settings, provider)
    if code is None:
        logger.warning("oauth callback missing code", provider=provider)
        return _login_redirect(
            "provider_unavailable", delete_cookie=True, settings=settings
        )

    try:
        token = await provider_impl.exchange_code(
            code=code, verifier=flow.verifier, redirect_uri=redirect_uri
        )
        profile = await provider_impl.fetch_profile(token=token)
    except OAuthProviderError:
        logger.warning("oauth provider unavailable", provider=provider, exc_info=True)
        return _login_redirect(
            "provider_unavailable", delete_cookie=True, settings=settings
        )

    # Ветка 5: find-or-create (одна транзакция).
    service = OAuthService(session, settings)
    try:
        _user, _access_token, refresh_raw, new_user = await service.login_with_provider(
            profile
        )
    except OAuthAccountCreationError:
        _emit_oauth_failed(provider, "oauth_failed")
        return _login_redirect("oauth_failed", delete_cookie=True, settings=settings)

    # Успех: access token НЕ проходит через redirect-URL — только штатная
    # refresh-cookie; SPA получает access существующим POST /api/auth/refresh.
    _emit_oauth_success(provider, new_user)
    response = RedirectResponse(url=flow.next, status_code=302)
    set_refresh_cookie(response, refresh_raw, settings)
    delete_flow_cookie(response, settings)
    return response
