from pydantic import BaseModel


class ProvidersResponse(BaseModel):
    """``GET /api/auth/providers`` — доступные способы входа.

    ``password`` в v1 всегда ``true`` (задел на будущие политики,
    design-brief.md § Контракты). Гео-фильтрация состава ``providers``
    подключается в T1.7 — на этой фазе состав равен активным провайдерам
    реестра без геоограничений.
    """

    providers: list[str]
    password: bool = True
