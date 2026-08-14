from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from siem_contracts import (
    AUTH_LOGIN_FAILED,
    AUTH_LOGIN_SUCCESS,
    AUTH_REFRESH_REPLAY_DETECTED,
    AUTH_REGISTER_FAILED,
    AUTH_REGISTER_SUCCESS,
    RATE_LIMIT_LOGIN_EXCEEDED,
    RATE_LIMIT_REFRESH_EXCEEDED,
    RATE_LIMIT_REGISTER_EXCEEDED,
)

from app.api.cookies import (
    RefreshCookie,
    cookie_deletion_headers,
    delete_refresh_cookie,
    set_refresh_cookie,
)
from app.api.deps import CurrentUser, DBSession, SettingsDep
from app.api.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.infra.client_ip import get_client_ip
from app.infra.rate_limit import RateLimiter
from app.services.auth import AuthService
from app.services.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    ReplayDetectedError,
    TokenExpiredError,
    UsernameAlreadyExistsError,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


RateLimiterDep = Annotated[RateLimiter, Depends(_get_rate_limiter)]


def _check_rate_limit(
    rate_limiter: RateLimiter,
    key: str,
    max_requests: int,
    window_seconds: int,
    event_type: str,
) -> None:
    allowed, retry_after = rate_limiter.is_allowed(key, max_requests, window_seconds)
    if not allowed:
        logger.warning(
            "rate limit exceeded",
            security_event=True,
            event_type=event_type,
            severity="warning",
            metadata={"key": key, "limit": max_requests, "window": window_seconds},
        )
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов, попробуйте позже",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: DBSession,
    settings: SettingsDep,
    rate_limiter: RateLimiterDep,
) -> TokenResponse:
    _check_rate_limit(
        rate_limiter,
        f"register:{get_client_ip(request, settings)}",
        3,
        3600,
        RATE_LIMIT_REGISTER_EXCEEDED,
    )
    service = AuthService(session, settings)
    try:
        user, access_token, refresh_raw = await service.register(
            body.name, body.password
        )
        logger.info(
            "user registered",
            security_event=True,
            event_type=AUTH_REGISTER_SUCCESS,
            severity="info",
            metadata={"username": body.name},
        )
    except UsernameAlreadyExistsError:
        logger.warning(
            "user registration failed",
            security_event=True,
            event_type=AUTH_REGISTER_FAILED,
            severity="warning",
            metadata={"username": body.name, "reason": "username_exists"},
        )
        raise HTTPException(status_code=409, detail="Имя уже занято") from None

    set_refresh_cookie(response, refresh_raw, settings)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DBSession,
    settings: SettingsDep,
    rate_limiter: RateLimiterDep,
) -> TokenResponse:
    ip = get_client_ip(request, settings)
    _check_rate_limit(
        rate_limiter, f"login:{body.name}:{ip}", 5, 60, RATE_LIMIT_LOGIN_EXCEEDED
    )
    service = AuthService(session, settings)
    try:
        user, access_token, refresh_raw = await service.login(body.name, body.password)
        logger.info(
            "user login success",
            security_event=True,
            event_type=AUTH_LOGIN_SUCCESS,
            severity="info",
            metadata={"username": body.name},
        )
    except InvalidCredentialsError:
        logger.warning(
            "user login failed",
            security_event=True,
            event_type=AUTH_LOGIN_FAILED,
            severity="warning",
            metadata={"username": body.name, "reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=401, detail="Неверное имя или пароль") from None

    set_refresh_cookie(response, refresh_raw, settings)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: DBSession,
    settings: SettingsDep,
    rate_limiter: RateLimiterDep,
    refresh_token: RefreshCookie = None,
) -> TokenResponse:
    _check_rate_limit(
        rate_limiter,
        f"refresh:{get_client_ip(request, settings)}",
        10,
        60,
        RATE_LIMIT_REFRESH_EXCEEDED,
    )
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Требуется вход")

    service = AuthService(session, settings)
    try:
        access_token, new_refresh_raw = await service.refresh(refresh_token)
    except (InvalidTokenError, TokenExpiredError):
        raise HTTPException(
            status_code=401, detail="Сессия истекла, войдите снова"
        ) from None
    except ReplayDetectedError:
        logger.warning(
            "token replay detected",
            security_event=True,
            event_type=AUTH_REFRESH_REPLAY_DETECTED,
            severity="critical",
        )
        raise HTTPException(
            status_code=401,
            detail="Обнаружено повторное использование токена — все сессии завершены",
            headers=cookie_deletion_headers(settings),
        ) from None

    set_refresh_cookie(response, new_refresh_raw, settings)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        name=user.name,
        is_admin=bool(user.is_admin),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    session: DBSession,
    settings: SettingsDep,
    refresh_token: RefreshCookie = None,
) -> MessageResponse:
    if refresh_token:
        service = AuthService(session, settings)
        await service.logout(refresh_token)
    delete_refresh_cookie(response, settings)
    return MessageResponse(detail="Вы вышли из аккаунта")
