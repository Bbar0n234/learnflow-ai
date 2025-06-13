## Проект генерации контента на базе LangGraph

### Использование Poetry

Проект предполагает управление зависимостями и виртуальной средой через `poetry`:
```bash
poetry init      # создание pyproject.toml
poetry add langchain langgraph fastapi uvicorn pydantic asyncpg websockets ...
poetry install   # установка
poetry run ...   # запуск приложений
```

---

### Базовая файловая структура
```
project_root/
├── pyproject.toml              # файл Poetry
├── settings.py                 # глобальные настройки (Pydantic)
├── core/
│   ├── graph.py                # сборка LangGraph
│   ├── graph_manager.py        # оркестрация (полный код ниже)
│   ├── state.py                # модель состояния
│   └── nodes/
│       ├── base.py             # FeedbackNode (полный код ниже)
│       ├── preprocessing.py    # download_video, get_transcription, clarify_context
│       ├── generation.py       # description_node, title_node, thumbnail_node, announce_node
│       └── publish.py          # request_thumbnail_node, publish_announce_node и сервисные узлы
├── api/
│   └── main.py                 # FastAPI эндпойнты
└── bot/
    └── main.py                 # Telegram-бот
```

---

### Основные компоненты
1. **FastAPI-сервис** – REST-эндпойнты для запуска/продолжения графа и запроса состояния.
2. **Telegram-бот** – пользовательский интерфейс поверх того же `GraphManager`.
3. **GraphManager** – единая точка входа; решает «start vs resume», хранит чекпоинты, пушит артефакты.
4. **HITL-узлы** – реализуют цикл «генерация → feedback → правка → approve».

---

### HITL: полный код `FeedbackNode`
```python
from abc import ABC, abstractmethod
from langchain_core.runnables.config import RunnableConfig
from langgraph.types import interrupt, Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from typing import Any, Dict
import logging

class FeedbackNode(ABC):
    """
    Абстрактный базовый класс для узлов, реализующих паттерн
    «генерация — обратная связь — правка — завершение».
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    @abstractmethod
    def is_initial(self, state) -> bool:
        """Нужно ли делать первую генерацию"""
        pass

    @abstractmethod
    def render_prompt(self, state, user_feedback: str = None) -> str:
        """Формирование промпта для LLM"""
        pass

    @abstractmethod
    def get_model(self):
        """Возвращает LLM/chain"""
        pass

    @abstractmethod
    def format_initial_response(self, response) -> str:
        pass

    @abstractmethod
    def is_approved(self, response) -> bool:
        pass

    @abstractmethod
    def get_next_node(self, state, approved: bool = False) -> str:
        pass

    @abstractmethod
    def get_user_prompt(self) -> str:
        pass

    @abstractmethod
    def get_update_on_approve(self, state, response) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_current_node_name(self) -> str:
        pass

    # ------- helpers -------
    def get_initial_update(self, response) -> Dict[str, Any]:
        formatted = self.format_initial_response(response)
        return {"feedback_messages": [AIMessage(content=formatted)]}

    def get_continue_update(self, state, user_feedback: str, response) -> Dict[str, Any]:
        formatted = self.format_initial_response(response)
        return {
            "feedback_messages": state.feedback_messages + [
                HumanMessage(content=user_feedback),
                AIMessage(content=formatted),
            ]
        }

    async def __call__(self, state, config: RunnableConfig) -> Command:
        thread_id = config["configurable"]["thread_id"]
        self.logger.debug(f"Processing {self.__class__.__name__} for thread {thread_id}")

        # 1. Первая генерация
        if self.is_initial(state):
            prompt = self.render_prompt(state)
            model = self.get_model()
            response = await model.ainvoke([SystemMessage(content=prompt)])
            return Command(
                goto=self.get_current_node_name(),
                update=self.get_initial_update(response),
            )

        # 2. Запрос обратной связи
        messages_for_user = [state.feedback_messages[-1].content]
        if len(state.feedback_messages) == 1:
            messages_for_user.append(self.get_user_prompt())
        interrupt_json = {"message": messages_for_user}
        user_feedback = interrupt(interrupt_json)

        # 3. Правка с учётом feedback
        prompt = self.render_prompt(state, user_feedback=user_feedback)
        model = self.get_model()
        messages = [SystemMessage(content=prompt)] + state.feedback_messages + [
            HumanMessage(content=user_feedback)
        ]
        response = await model.ainvoke(messages)

        # 4. Проверка approve
        if self.is_approved(response):
            return Command(
                goto=self.get_next_node(state, approved=True),
                update=self.get_update_on_approve(state, response),
            )
        return Command(
            goto=self.get_current_node_name(),
            update=self.get_continue_update(state, user_feedback, response),
        )
```

---

### GraphManager – полный код
```python
"""
GraphManager – единая оболочка вокруг LangGraph workflow.
Отвечает за:
• lazy-инициализацию БД чекпоинтов
• запуск / продолжение графа
• передачу сообщений HITL-узлов наружу
• пуш артефактов (опционально) в GitHub
"""

import os, uuid, logging
from typing import Dict, Any, Optional, List

from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from core.graph import create_workflow
from core.state import GeneralState
from settings import get_settings
from integrations.github import GitHubArtifactPusher, GitHubConfig

NODE_DESCRIPTIONS = {
    "download_video":       "Загрузка видео",
    "get_transcription":    "Получение транскрипции",
    "clarify_context":      "Уточнение контекста",
    "description_node":     "Генерация и правка описания",
    "title_node":           "Генерация и правка заголовка",
    "thumbnail_node":       "Генерация и правка превью",
    "announce_node":        "Генерация и правка анонса",
    "request_thumbnail_node": "Запрос обложки",
    "publish_announce_node":  "Публикация анонса",
    None:                   "Готов к новой транскрипции",
}

logger = logging.getLogger(__name__)

class GraphManager:
    """
    Управляет единым экземпляром LangGraph для множества пользователей.
    Состояния разделяются по thread_id в Postgres-checkpointer.
    """

    def __init__(self) -> None:
        self.workflow = create_workflow()
        self.settings = get_settings()

        self._setup_done = False            # чтобы инициализацию БД делать один раз

        # GitHub integration (необязательно)
        self.github_pusher: Optional[GitHubArtifactPusher] = None
        if self.settings.llm.is_github_configured():
            cfg = GitHubConfig(
                token=self.settings.llm.github_token,
                repository=self.settings.llm.github_repository,
                branch=self.settings.llm.github_branch,
                base_path=self.settings.llm.github_base_path,
            )
            self.github_pusher = GitHubArtifactPusher(cfg)

        # хранилище пользовательских настроек
        self.user_settings: Dict[str, Dict[str, Any]] = {}

    # ---------- internal helpers ----------

    async def _ensure_setup(self):
        if self._setup_done:
            return
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.llm.database_conn_string
        ) as saver:
            await saver.setup()
        self._setup_done = True

    async def _get_state(self, thread_id: str):
        await self._ensure_setup()
        cfg = {"configurable": {"thread_id": thread_id}}
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.llm.database_conn_string
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            return await graph.aget_state(cfg)

    async def _update_state(self, thread_id: str, update: Dict[str, Any]):
        await self._ensure_setup()
        cfg = {"configurable": {"thread_id": thread_id}}
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.llm.database_conn_string
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            await graph.aupdate_state(cfg, update)

    async def delete_thread(self, thread_id: str):
        await self._ensure_setup()
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.llm.database_conn_string
        ) as saver:
            await saver.adelete_thread(thread_id)

    # ---------- github artifacts ----------

    async def _push_artifacts_to_github(self, thread_id: str, state_vals: Dict[str, Any]):
        if not self.github_pusher:
            return

        if not any(
            state_vals.get(k, "") for k in
            ("description", "title", "thumbnail_caption", "telegram_announce")
        ):
            return                          # нечего пушить

        res = await self.github_pusher.push_artifacts(
            thread_id=thread_id,
            description=state_vals.get("description", ""),
            title=state_vals.get("title", ""),
            thumbnail_caption=state_vals.get("thumbnail_caption", ""),
            telegram_announce=state_vals.get("telegram_announce", ""),
            video_url=state_vals.get("video_url", ""),
        )
        if res.get("success"):
            await self._update_state(
                thread_id,
                {"github_artifacts_path": os.path.join(
                    self.settings.llm.github_artifacts_base_url,
                    res["file_path"]
                )}
            )

    # ---------- public API ----------

    async def process_step(self, thread_id: str, query: str) -> Dict[str, Any]:
        """
        Единственный entry-point:
        • если thread_id пуст – создаёт новый
        • если в состоянии нет values – стартует новый run
        • иначе – продолжает через Command(resume=…)
        """
        if not thread_id:
            thread_id = str(uuid.uuid4())

        state = await self._get_state(thread_id)
        cfg = {"configurable": {"thread_id": thread_id}}

        # определяем input_state
        if not state.values:                           # fresh run
            if len(query) < 200:
                input_state = GeneralState(video_url=query)
            else:
                input_state = GeneralState(raw_transcript=query)
        else:                                          # continue
            input_state = Command(resume=query)

        # запускаем/продолжаем граф
        await self._ensure_setup()
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.llm.database_conn_string
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            async for event in graph.astream(
                input_state, cfg, stream_mode="updates"
            ):
                # github-push триггерим по завершению title_node
                if "title_node" in event:
                    vals = await self._get_state(thread_id)
                    await self._push_artifacts_to_github(thread_id, vals)

                # HITL сообщения наружу
                for node_name, node_data in event.items():
                    if isinstance(node_data, dict) and node_data.get("return_messages"):
                        # здесь можно пробросить их через WebSocket / Telegram
                        await self._update_state(thread_id, {"return_messages": []})

        # после завершения / остановки
        final_state = await self._get_state(thread_id)
        if final_state.interrupts:
            interrupt_data = final_state.interrupts[0].value
            msgs = interrupt_data.get("message", [str(interrupt_data)])
            return {"thread_id": thread_id, "result": msgs}

        # happy path – всё закончено
        # (можно удалить thread, если не нужен)
        return {
            "thread_id": thread_id,
            "result": "Готово 🎉 – присылайте следующее видео!"
        }

    async def get_current_step(self, thread_id: str) -> Dict[str, str]:
        state = await self._get_state(thread_id)
        node = None
        if state and state.interrupts:
            node = state.interrupts[0].ns[0].split(':')[0]
        return {
            "node": node,
            "description": NODE_DESCRIPTIONS.get(node, NODE_DESCRIPTIONS[None])
        }
```

---

### REST API (FastAPI)
| Метод | Путь | Описание |
|-------|------|----------|
| GET  | /          | Проверка работы |
| GET  | /health    | Health-probe |
| POST | /process   | Запуск/продолжение графа `{thread_id, message}` |
| GET  | /state/{thread_id} | Текущее состояние |
| DELETE | /thread/{thread_id} | Очистка чекпоинтов |