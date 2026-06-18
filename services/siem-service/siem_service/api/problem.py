"""RFC 9457 Problem Details — единый формат тела ошибок REST API.

Зеркало ``backend/app/api/problem.py``: сервисы — самостоятельные runtime'ы,
общего пакета под этот модуль нет.

Барьерный стек (три слоя, от специфичного к общему):
  1. AppError → доменный статус problem+json (4xx/409/422).
  2. Инфра-исключения (DBAPIError→503, TimeoutError→504) + лог exc_info.
  3. generic Exception (last-resort) — перехватывается в middleware в main.py;
     CORSMiddleware регистрируется последним и потому оборачивает этот
     обработчик (он самый внешний в стеке), так что 500-ответ проходит обратно
     через CORS и получает CORS-заголовки.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from siem_service.exceptions import AppError

logger = structlog.get_logger()

PROBLEM_CONTENT_TYPE = "application/problem+json"
TYPE_PREFIX = "urn:learnflow:"


def problem_response(
    *,
    status: int,
    detail: str | None = None,
    type_: str | None = None,
    headers: Mapping[str, str] | None = None,
    **extensions: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": type_ or "about:blank",
        "title": HTTPStatus(status).phrase,
        "status": status,
    }
    if detail is not None:
        body["detail"] = detail
    body.update(extensions)
    return JSONResponse(
        status_code=status,
        content=body,
        headers=headers,
        media_type=PROBLEM_CONTENT_TYPE,
    )


# ---------------------------------------------------------------------------
# Layer 1: AppError → domain problem+json
# ---------------------------------------------------------------------------


async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    # Server-side AppError (5xx) must leave a trace with exc_info. 4xx are
    # client errors, not server faults — not logged as error (§ Logging
    # антипаттерны).
    if exc.status >= 500:
        logger.error(
            "application error",
            code=exc.code,
            status=exc.status,
            exc_info=exc,
        )
    type_ = TYPE_PREFIX + exc.code
    extensions = {k: jsonable_encoder(v) for k, v in exc.extensions.items()}
    return problem_response(
        status=exc.status,
        detail=exc.detail,
        type_=type_,
        **extensions,
    )


# ---------------------------------------------------------------------------
# Layer 2: infrastructure exceptions → 503/504
# ---------------------------------------------------------------------------


async def _infra_exception_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    logger.error("database error", exc_info=True)
    return problem_response(
        status=503,
        detail="Database unavailable",
        type_=TYPE_PREFIX + "db-unavailable",
    )


async def _timeout_exception_handler(
    request: Request, exc: TimeoutError
) -> JSONResponse:
    logger.error("dependency timeout", exc_info=True)
    return problem_response(
        status=504,
        detail="Upstream dependency timed out",
        type_=TYPE_PREFIX + "timeout",
    )


# ---------------------------------------------------------------------------
# Layer 2b: Starlette HTTPException → problem+json (existing, kept)
# ---------------------------------------------------------------------------


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    # Структурный detail ({"error": <code>, "message": ..., ...}) →
    # машинный type + остальные ключи как расширения problem-объекта.
    if isinstance(exc.detail, dict):
        payload = dict(exc.detail)
        code = payload.pop("error", None)
        message = payload.pop("message", None)
        type_ = TYPE_PREFIX + str(code).replace("_", "-") if code else None
        return problem_response(
            status=exc.status_code,
            detail=message,
            type_=type_,
            headers=exc.headers,
            **payload,
        )
    return problem_response(
        status=exc.status_code,
        detail=str(exc.detail) if exc.detail is not None else None,
        headers=exc.headers,
    )


# ---------------------------------------------------------------------------
# Validation — narrow to loc/msg/type only, drop ctx/input/url
# ---------------------------------------------------------------------------


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    safe_errors = [
        {"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")}
        for e in exc.errors()
    ]
    return problem_response(
        status=422,
        detail="Request validation failed",
        type_=TYPE_PREFIX + "validation-error",
        errors=safe_errors,
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DBAPIError, _infra_exception_handler)  # type: ignore[arg-type]
    # asyncio.TimeoutError is a subclass of TimeoutError (Python 3.11+), so
    # registering TimeoutError covers both.
    app.add_exception_handler(TimeoutError, _timeout_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(asyncio.TimeoutError, _timeout_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
