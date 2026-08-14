from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base domain exception.

    Carries a machine-readable ``code`` (kebab-case), a default HTTP ``status``,
    and a client-safe ``detail`` message.  No transport knowledge — no fastapi /
    HTTP imports here.

    Mirror of ``backend/app/services/exceptions.py``: services are separate
    runtimes; there is no shared package for this module.
    """

    code: str = "error"
    status: int = 500

    def __init__(
        self,
        detail: str | None = None,
        *,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        self.detail: str = detail or "Внутренняя ошибка — попробуйте позже"
        self.extensions: dict[str, Any] = extensions or {}
        super().__init__(self.detail)


class NotFoundError(AppError):
    code = "entity-not-found"
    status = 404

    def __init__(self, detail: str = "Ресурс не найден") -> None:
        super().__init__(detail)


class ConflictError(AppError):
    code = "conflict"
    status = 409

    def __init__(
        self, detail: str = "Конфликт данных — обновите страницу и попробуйте снова"
    ) -> None:
        super().__init__(detail)
