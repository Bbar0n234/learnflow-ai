"""Seed deterministic demo data for visual review (feat-004, phase DP).

Variant A (approved by architect): write data straight through the existing
code-paths — no LLM, no graph run, no schema change. The script is idempotent:
re-running does not duplicate rows. Relational entities (User/Project/ThreadView/
Artifact) are matched by their natural keys; chat messages are written to the
LangGraph checkpointer with deterministic message ids so the ``add_messages``
reducer replaces them in place; the Knowledge Sphere is written through
``LangGraphSphereService.update`` which is replace-by-section by design.

Dev/test-only. Never run against production data.

Usage: make seed-demo
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from app.config import Settings
from app.infra.db import create_engine, create_session_factory
from app.infra.langgraph import create_checkpointer, create_store
from app.models.user import User
from app.repositories.artifact import ArtifactRepository
from app.repositories.project import ProjectRepository
from app.repositories.thread_view import ThreadViewRepository
from app.repositories.user import UserRepository
from app.services.security import hash_password
from app.services.sphere import LangGraphSphereService
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from sqlalchemy import update

logger = structlog.get_logger()

# --- Demo credentials (dev/test-only seed) -------------------------------------
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo-pass-1234"  # noqa: S105 — intentional seed credential
DEMO_PROJECT_NAME = "Демо: Высшая математика"

# Deterministic namespace so message ids are stable across re-runs.
_SEED_NS = uuid.UUID("0a5e6d00-0000-4000-8000-000000000004")

# Fixed base time → deterministic ``created_at`` ordering in the chat history.
_BASE_TS = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)


def _msg_id(thread_id: uuid.UUID, slot: str) -> str:
    """Deterministic message id for (thread, slot) — stable across re-runs."""
    return str(uuid.uuid5(_SEED_NS, f"{thread_id}:{slot}"))


def _ts(minute: int) -> str:
    """ISO ``created_at`` at a fixed offset from the base time."""
    return _BASE_TS.replace(minute=minute).isoformat()


# --- Static content ------------------------------------------------------------

_CHAT1_TITLE = "Цепное правило дифференцирования"
_CHAT2_TITLE = "С чего начать линейную алгебру"
_CHAT3_TITLE = "Пределы и непрерывность"

_INLINE_ARTIFACT_TITLE = "Конспект: цепное правило"
_INLINE_ARTIFACT_TYPE = "summary"
_INLINE_ARTIFACT_CONTENT = """# Цепное правило дифференцирования

Если `y = f(g(x))`, то производная вычисляется как произведение производных:

```
y' = f'(g(x)) · g'(x)
```

## Пошаговый пример

Найдём производную функции `y = sin(x²)`.

1. Внешняя функция: `f(u) = sin(u)`, её производная `f'(u) = cos(u)`.
2. Внутренняя функция: `g(x) = x²`, её производная `g'(x) = 2x`.
3. Собираем по правилу: `y' = cos(x²) · 2x = 2x·cos(x²)`.

## Типичные ошибки

- Забывают умножить на производную внутренней функции.
- Путают порядок применения при вложенности глубже двух уровней.
"""

# Standalone artifacts — a spread of types so the artifact list and the
# type-specific viewers (group B) render on real rows. slides/image/audio
# viewers are mock-driven on the frontend, so freeform text content is fine.
_STANDALONE_ARTIFACTS: list[dict[str, str]] = [
    {
        "title": "План изучения линейной алгебры",
        "type": "plan",
        "content": (
            "# План изучения линейной алгебры\n\n"
            "1. Векторы и операции над ними\n"
            "2. Матрицы и матричные операции\n"
            "3. Системы линейных уравнений\n"
            "4. Определители\n"
            "5. Собственные значения и векторы\n"
        ),
    },
    {
        "title": "Структура курса математического анализа",
        "type": "outline",
        "content": (
            "# Математический анализ — структура курса\n\n"
            "## Модуль 1. Пределы\n- Предел последовательности\n- Предел функции\n\n"
            "## Модуль 2. Производные\n- Определение\n- Правила дифференцирования\n\n"
            "## Модуль 3. Интегралы\n- Неопределённый интеграл\n- Определённый интеграл\n"
        ),
    },
    {
        "title": "Численное дифференцирование на Python",
        "type": "code",
        "content": (
            "# Численная производная методом центральной разности\n\n"
            "```python\n"
            "def derivative(f, x, h=1e-6):\n"
            "    return (f(x + h) - f(x - h)) / (2 * h)\n\n\n"
            "print(derivative(lambda x: x ** 2, 3))  # ≈ 6.0\n"
            "```\n"
        ),
    },
    {
        "title": "Презентация: Производные и их применение",
        "type": "slides",
        "content": "Слайды по теме производных (демо-артефакт типа slides).",
    },
    {
        "title": "Схема: геометрический смысл производной",
        "type": "image",
        "content": "Иллюстрация касательной к графику (демо-артефакт типа image).",
    },
    {
        "title": "Аудиолекция: введение в пределы",
        "type": "audio",
        "content": "Запись вводной лекции о пределах (демо-артефакт типа audio).",
    },
]

_SPHERE_CONTENT = """## Цель обучения
_Чего хочет достичь студент в этом проекте_

Освоить базовый математический анализ и линейную алгебру до уровня уверенного
решения типовых задач: пределы, производные, интегралы, матрицы и СЛАУ.

## Производные
_Ключевые правила дифференцирования_

- Производная суммы равна сумме производных.
- Производная произведения: `(uv)' = u'v + uv'`.
- Цепное правило для сложной функции: `f(g(x))' = f'(g(x))·g'(x)`.

## Линейная алгебра
_Опорные темы и порядок изучения_

Сначала векторы и матрицы, затем системы линейных уравнений и определители.
Финал блока — собственные значения и собственные векторы.

## Договорённости
_Предпочтения студента по формату объяснений_

Объяснять с пошаговыми примерами и отмечать типичные ошибки. Формулы — в виде
коротких блоков кода, без тяжёлой нотации.
"""


def _build_seed_graph(checkpointer: Any) -> Any:
    """Minimal MessagesState graph used only to persist seeded messages.

    Reuses LangGraph's own checkpoint serialization (same shape the runtime graph
    reads back) instead of hand-constructing checkpoint internals.
    """

    def _passthrough(state: MessagesState) -> dict:
        return {}

    builder = StateGraph(MessagesState)
    builder.add_node("seed", _passthrough)
    builder.add_edge(START, "seed")
    builder.add_edge("seed", END)
    return builder.compile(checkpointer=checkpointer)


def _chat1_messages(thread_id: uuid.UUID, inline_artifact_id: str) -> list[Any]:
    """Full flow: user → tool-calling AI → tool result → final AI (with artifact)."""
    tool_call_id = "call_chain_rule_1"
    return [
        HumanMessage(
            id=_msg_id(thread_id, "h1"),
            content=(
                "Объясни цепное правило дифференцирования и покажи пример "
                "с пошаговым решением."
            ),
            additional_kwargs={"created_at": _ts(0)},
        ),
        AIMessage(
            id=_msg_id(thread_id, "ai-tool"),
            content="",
            tool_calls=[
                {
                    "name": "create_artifact",
                    "args": {
                        "title": _INLINE_ARTIFACT_TITLE,
                        "type": _INLINE_ARTIFACT_TYPE,
                        "content": "(полный конспект по цепному правилу)",
                    },
                    "id": tool_call_id,
                    "type": "tool_call",
                }
            ],
            additional_kwargs={"created_at": _ts(1)},
        ),
        ToolMessage(
            id=_msg_id(thread_id, "tool"),
            tool_call_id=tool_call_id,
            name="create_artifact",
            content=(
                f"Artifact saved: '{_INLINE_ARTIFACT_TITLE}' "
                f"(type={_INLINE_ARTIFACT_TYPE}, id={inline_artifact_id})"
            ),
            additional_kwargs={"created_at": _ts(1)},
        ),
        AIMessage(
            id=_msg_id(thread_id, "ai-final"),
            content=(
                "Цепное правило позволяет дифференцировать сложную функцию: "
                "производная внешней функции умножается на производную внутренней.\n\n"
                "Я оформил подробный конспект с пошаговым примером — он прикреплён "
                "к этому сообщению."
            ),
            additional_kwargs={"created_at": _ts(2)},
        ),
    ]


def _chat2_messages(thread_id: uuid.UUID) -> list[Any]:
    """Simple two-turn exchange without tools."""
    return [
        HumanMessage(
            id=_msg_id(thread_id, "h1"),
            content=(
                "Я только начинаю изучать линейную алгебру. С каких тем лучше начать?"
            ),
            additional_kwargs={"created_at": _ts(0)},
        ),
        AIMessage(
            id=_msg_id(thread_id, "ai1"),
            content=(
                "Хороший порядок такой:\n\n"
                "1. Векторы — сложение, умножение на число, скалярное произведение.\n"
                "2. Матрицы — операции и умножение.\n"
                "3. Системы линейных уравнений и метод Гаусса.\n\n"
                "Эти три темы дают фундамент для всего остального."
            ),
            additional_kwargs={"created_at": _ts(1)},
        ),
        HumanMessage(
            id=_msg_id(thread_id, "h2"),
            content="А матрицы зачем нужны на практике?",
            additional_kwargs={"created_at": _ts(2)},
        ),
        AIMessage(
            id=_msg_id(thread_id, "ai2"),
            content=(
                "Матрицы — компактный способ описывать линейные преобразования "
                "и решать системы уравнений. Они повсюду: компьютерная графика, "
                "машинное обучение, физические модели."
            ),
            additional_kwargs={"created_at": _ts(3)},
        ),
    ]


async def _ensure_user(session: Any) -> User:
    repo = UserRepository(session)
    user = await repo.get_by_name(DEMO_USERNAME)
    if user is None:
        user = await repo.create(
            User(
                name=DEMO_USERNAME,
                password_hash=hash_password(DEMO_PASSWORD),
            )
        )
        logger.info("seed user created", username=DEMO_USERNAME)
    else:
        logger.info("seed user exists", username=DEMO_USERNAME)
    # Idempotent admin grant (needed for security screens).
    if not user.is_admin:
        await session.execute(
            update(User).where(User.id == user.id).values(is_admin=True)
        )
        user.is_admin = True
    return user


async def _ensure_project(session: Any, user_id: uuid.UUID) -> uuid.UUID:
    repo = ProjectRepository(session)
    existing = await repo.list_by_user(user_id, limit=100)
    for project in existing:
        if project.name == DEMO_PROJECT_NAME:
            logger.info("seed project exists", project_id=str(project.id))
            return project.id
    project = await repo.create(user_id=user_id, name=DEMO_PROJECT_NAME)
    logger.info("seed project created", project_id=str(project.id))
    return project.id


async def _ensure_thread(session: Any, project_id: uuid.UUID, title: str) -> uuid.UUID:
    repo = ThreadViewRepository(session)
    existing = await repo.list_by_project(project_id, limit=100)
    for thread in existing:
        if thread.title == title:
            return thread.thread_id
    thread = await repo.create(project_id=project_id, title=title)
    logger.info("seed thread created", thread_id=str(thread.thread_id), title=title)
    return thread.thread_id


async def _ensure_artifact(
    session: Any,
    project_id: uuid.UUID,
    *,
    title: str,
    type: str,
    content: str,
    thread_id: uuid.UUID | None = None,
) -> uuid.UUID:
    repo = ArtifactRepository(session)
    existing = await repo.list_by_project(project_id, limit=200)
    for artifact in existing:
        if artifact.title == title:
            return artifact.id
    artifact = await repo.create(
        project_id=project_id,
        title=title,
        type=type,
        content=content,
        thread_id=thread_id,
    )
    logger.info("seed artifact created", artifact_id=str(artifact.id), type=type)
    return artifact.id


async def seed_demo() -> int:
    settings = Settings()
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    # --- Relational entities (single committed transaction) --------------------
    async with session_factory() as session, session.begin():
        user = await _ensure_user(session)
        project_id = await _ensure_project(session, user.id)

        chat1_id = await _ensure_thread(session, project_id, _CHAT1_TITLE)
        chat2_id = await _ensure_thread(session, project_id, _CHAT2_TITLE)
        await _ensure_thread(session, project_id, _CHAT3_TITLE)

        # Inline artifact for chat 1, linked to the final AI message.
        inline_artifact_id = await _ensure_artifact(
            session,
            project_id,
            title=_INLINE_ARTIFACT_TITLE,
            type=_INLINE_ARTIFACT_TYPE,
            content=_INLINE_ARTIFACT_CONTENT,
            thread_id=chat1_id,
        )
        await ArtifactRepository(session).set_message_id(
            [inline_artifact_id], _msg_id(chat1_id, "ai-final")
        )

        for spec in _STANDALONE_ARTIFACTS:
            await _ensure_artifact(
                session,
                project_id,
                title=spec["title"],
                type=spec["type"],
                content=spec["content"],
            )

    await engine.dispose()

    # --- LangGraph persistence (checkpointer for messages, store for sphere) ---
    lg_db_url = settings.langgraph_database_url
    async with (
        create_store(lg_db_url) as store,
        create_checkpointer(lg_db_url) as checkpointer,
    ):
        await store.setup()
        await checkpointer.setup()

        graph = _build_seed_graph(checkpointer)

        # Messages — idempotent via deterministic ids + add_messages dedup.
        await graph.ainvoke(
            {"messages": _chat1_messages(chat1_id, str(inline_artifact_id))},
            config={"configurable": {"thread_id": str(chat1_id)}},
        )
        await graph.ainvoke(
            {"messages": _chat2_messages(chat2_id)},
            config={"configurable": {"thread_id": str(chat2_id)}},
        )
        logger.info("seed messages written", chats=[str(chat1_id), str(chat2_id)])

        # Knowledge Sphere — replace-by-section, idempotent by design.
        sphere = LangGraphSphereService(store)
        await sphere.update(project_id=project_id, content=_SPHERE_CONTENT)
        logger.info("seed sphere written", project_id=str(project_id))

    print("Demo data seeded (idempotent).")
    print(f"  login:    {DEMO_USERNAME}")
    print(f"  password: {DEMO_PASSWORD}")
    print(f"  project:  {DEMO_PROJECT_NAME}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(seed_demo()))


if __name__ == "__main__":
    main()
