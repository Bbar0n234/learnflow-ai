from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Response

from app.config import Settings

COOKIE_NAME = "refresh_token"

# Общий тип DI для `refresh_token`-cookie — используется обоими роутерами
# (`routes/auth.py`, `routes/oauth.py`), не только владельцем cookie.
RefreshCookie = Annotated[str | None, Cookie(alias=COOKIE_NAME)]


def set_refresh_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/auth",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )


def delete_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/api/auth",
    )


def cookie_deletion_headers(settings: Settings) -> dict[str, str]:
    """Set-Cookie удаления refresh-cookie для HTTPException-ответов.

    Заголовки injected `Response` теряются, когда handler поднимает
    HTTPException (FastAPI строит новый ответ), — передаём удаление cookie
    через `HTTPException(headers=...)`.
    """
    response = Response()
    delete_refresh_cookie(response, settings)
    return {"set-cookie": response.headers["set-cookie"]}
