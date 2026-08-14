from pydantic import BaseModel


class ProvidersResponse(BaseModel):
    """``GET /api/auth/providers`` — доступные способы входа.

    ``password`` в v1 всегда ``true`` (задел на будущие политики,
    design-brief.md § Контракты). Состав ``providers`` — активные провайдеры
    реестра, отфильтрованные гео-gate'ом (design-brief.md § Гео-gate).
    """

    providers: list[str]
    password: bool = True
