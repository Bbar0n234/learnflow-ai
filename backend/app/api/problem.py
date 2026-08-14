"""RFC 9457 Problem Details — единый формат тела ошибок REST API.

Все ошибки сервиса (HTTPException, доменные AppError, инфра-исключения, generic)
сериализуются в ``application/problem+json``:
  ``type`` / ``title`` / ``status`` / ``detail`` + extensions.

Машинно-различимые ошибки получают ``type`` вида ``urn:learnflow:<code>``;
для остальных ``type`` = ``about:blank`` и клиент ориентируется на ``status``.

Барьерный стек (от специфичного к общему):
  1. AppError → доменный статус problem+json (4xx/409/422).
  1b. WorkspacePathError (app.storage.workspace, ADR-032) → 422. Не входит в
      AppError-иерархию — `app.storage` лежит ниже `app.services` в контракте
      import-linter и не может импортировать `AppError` (см. класса докстринг
      в workspace.py). Отдельный узкий handler здесь — то самое «место,
      которому позволено» это исключение поймать.
  2. Инфра-исключения (DBAPIError→503, TimeoutError→504) + лог exc_info.
  3. generic Exception (last-resort) — перехватывается в request_id_middleware
     в main.py; CORSMiddleware регистрируется последним и потому оборачивает
     этот обработчик (он самый внешний в стеке), так что 500-ответ проходит
     обратно через CORS и получает CORS-заголовки (F-API-01).
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

from app.services.exceptions import AppError
from app.storage.workspace import WorkspacePathError

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
    # Server-side AppError (UpstreamUnavailableError 502/503, EncryptionError
    # 500, …) must leave a trace with exc_info. 4xx are client errors, not
    # server faults — not logged as error (§ Logging антипаттерны).
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
# Layer 1b: WorkspacePathError → 422 (path escaped both workspace roots)
# ---------------------------------------------------------------------------


async def _workspace_path_error_handler(
    request: Request, exc: WorkspacePathError
) -> JSONResponse:
    # 422, not 404: the request itself is malformed/adversarial (the resolved
    # path escapes both the project workspace and /skills), the same class of
    # rejection as SecurityPolicyViolationError — distinct from a syntactically
    # valid path whose file just doesn't exist (a route-local 404, § REST
    # артефакты). The security log (`agent.runtime.path_denied`) already fired
    # inside `Workspace.resolve_path`/`resolve_skill_path` — no exc_info here.
    return problem_response(
        status=422,
        detail=f"Недопустимый путь: {exc.path!r}",
        type_=TYPE_PREFIX + "invalid-path",
        reason=exc.reason,
    )


# ---------------------------------------------------------------------------
# Layer 2: infrastructure exceptions → 503/504
# ---------------------------------------------------------------------------


async def _infra_exception_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    logger.error("database error", exc_info=True)
    return problem_response(
        status=503,
        detail="База данных недоступна, попробуйте позже",
        type_=TYPE_PREFIX + "db-unavailable",
    )


async def _timeout_exception_handler(
    request: Request, exc: TimeoutError
) -> JSONResponse:
    logger.error("dependency timeout", exc_info=True)
    return problem_response(
        status=504,
        detail="Внешний сервис не ответил вовремя, попробуйте позже",
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
# Validation — F-API-14: narrow to loc/msg/type only, drop ctx/input/url
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
        detail="Запрос не прошёл валидацию",
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


# `register_problem_handlers` above is one of the `problem-mirrors`-checked
# defs (arch_checker, doc/tech/arch-checker.md) — its AST must stay identical
# to `siem_service/api/problem.py`'s copy, byte-for-byte modulo docstrings.
# `WorkspacePathError` has no SIEM-side equivalent (siem doesn't run agent
# tools or REST artifact routes), so its registration lives in a separate,
# unchecked function instead of a new line inside the mirrored one — kept the
# mirror intact instead of forking it further apart.
def register_workspace_path_error_handler(app: FastAPI) -> None:
    app.add_exception_handler(WorkspacePathError, _workspace_path_error_handler)  # type: ignore[arg-type]
