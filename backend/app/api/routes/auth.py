from __future__ import annotations

from fastapi import APIRouter, Cookie, HTTPException, Request, Response

from app.api.deps import CurrentUser, DBSession
from app.api.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.config import Settings
from app.infra.rate_limit import rate_limiter
from app.services.auth import AuthService
from app.services.exceptions import (
    InvalidCredentialsError,
    InvalidTokenError,
    ReplayDetectedError,
    TokenExpiredError,
    UsernameAlreadyExistsError,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_NAME = "refresh_token"


def _get_settings() -> Settings:
    return Settings()


def _check_rate_limit(key: str, max_requests: int, window_seconds: int) -> None:
    allowed, retry_after = rate_limiter.is_allowed(key, max_requests, window_seconds)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests",
            headers={"Retry-After": str(retry_after)},
        )


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/auth",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def _delete_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=_COOKIE_NAME,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/auth",
    )


@router.post("/register", response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    session: DBSession,
) -> TokenResponse:
    _check_rate_limit(f"register:{_get_client_ip(request)}", 3, 3600)
    settings = _get_settings()
    service = AuthService(session, settings)
    try:
        _user, access_token, refresh_raw = await service.register(
            body.name, body.password
        )
    except UsernameAlreadyExistsError:
        raise HTTPException(status_code=409, detail="Username already exists") from None

    _set_refresh_cookie(response, refresh_raw, settings)
    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: DBSession,
) -> TokenResponse:
    ip = _get_client_ip(request)
    _check_rate_limit(f"login:{body.name}:{ip}", 5, 60)
    settings = _get_settings()
    service = AuthService(session, settings)
    try:
        _user, access_token, refresh_raw = await service.login(body.name, body.password)
    except InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="Invalid credentials") from None

    _set_refresh_cookie(response, refresh_raw, settings)
    return TokenResponse(access_token=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    session: DBSession,
    refresh_token: str | None = Cookie(None),
) -> TokenResponse:
    _check_rate_limit(f"refresh:{_get_client_ip(request)}", 10, 60)
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    settings = _get_settings()
    service = AuthService(session, settings)
    try:
        access_token, new_refresh_raw = await service.refresh(refresh_token)
    except (InvalidTokenError, TokenExpiredError):
        raise HTTPException(
            status_code=401, detail="Invalid or expired refresh token"
        ) from None
    except ReplayDetectedError:
        _delete_refresh_cookie(response, settings)
        raise HTTPException(
            status_code=401, detail="Token reuse detected, all sessions revoked"
        ) from None

    _set_refresh_cookie(response, new_refresh_raw, settings)
    return TokenResponse(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse(id=str(user.id), name=user.name)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    response: Response,
    session: DBSession,
    refresh_token: str | None = Cookie(None),
) -> MessageResponse:
    settings = _get_settings()
    if refresh_token:
        service = AuthService(session, settings)
        await service.logout(refresh_token)
    _delete_refresh_cookie(response, settings)
    return MessageResponse(detail="Logged out")
