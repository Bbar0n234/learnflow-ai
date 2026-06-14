"""RFC 9457 Problem Details — единый формат тела ошибок REST API.

Зеркало ``backend/app/api/problem.py``: сервисы — самостоятельные runtime'ы,
общего пакета под этот модуль нет.
"""

from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

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


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
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


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return problem_response(
        status=422,
        detail="Request validation failed",
        type_=TYPE_PREFIX + "validation-error",
        errors=jsonable_encoder(exc.errors()),
    )


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)  # type: ignore[arg-type]
