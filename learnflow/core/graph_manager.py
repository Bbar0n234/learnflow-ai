"""
GraphManager – единая оболочка вокруг LangGraph workflow.
Отвечает за:
• lazy-инициализацию БД чекпоинтов
• запуск / продолжение графа
• передачу сообщений HITL-узлов наружу
• пуш артефактов
• трассировку в LangFuse
Адаптирован из project_documentation.md для ExamState.
"""

import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple, Callable

from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langfuse.callback import CallbackHandler

from .graph import create_workflow
from .state import ExamState
from ..config.settings import get_settings
from ..services.artifacts_manager import LocalArtifactsManager, ArtifactsConfig


NODE_DESCRIPTIONS = {
    "input_processing": "Обработка пользовательского ввода",
    "generating_content": "Генерация обучающего материала",
    "recognition_handwritten": "Распознавание рукописных конспектов",
    "synthesis_material": "Синтез финального материала",
    "edit_material": "Итеративное редактирование материала",
    "generating_questions": "Генерация и правка gap questions",
    "answer_question": "Генерация ответов на вопросы",
    None: "Готов к новому экзаменационному вопросу",
}

logger = logging.getLogger(__name__)


class GraphManager:
    """
    Управляет единым экземпляром LangGraph для множества пользователей.
    Состояния разделяются по thread_id в Postgres-checkpointer.
    """

    # Конфигурация артефактов для каждого узла
    NODE_ARTIFACT_CONFIG: Dict[str, Dict[str, Any]] = {
        "generating_content": {
            "condition": lambda node_data, state: bool(node_data.get("generated_material")),
            "handler": "_save_learning_material"
        },
        "recognition_handwritten": {
            "condition": lambda node_data, state: bool(node_data.get("recognized_notes")),
            "handler": "_save_recognized_notes"
        },
        "synthesis_material": {
            "condition": lambda node_data, state: bool(node_data.get("synthesized_material")),
            "handler": "_save_synthesized_material"
        },
        "edit_material": {
            "condition": lambda node_data, state: node_data.get("last_action") == "edit",
            "handler": "_save_synthesized_material"  # Тот же метод, перезапись
        },
        "generating_questions": {
            "condition": lambda node_data, state: bool(node_data.get("gap_questions")),
            "handler": "_save_gap_questions"
        },
        "answer_question": {
            "condition": lambda node_data, state: bool(node_data.get("gap_q_n_a")),
            "handler": "_save_answers"
        }
    }

    def __init__(self) -> None:
        self.workflow = create_workflow()
        self.settings = get_settings()

        self._setup_done = False  # чтобы инициализацию БД делать один раз

        # LangFuse integration
        self.langfuse_handler = CallbackHandler()

        # Словарь для хранения session_id для каждого пользователя
        # Ключ - thread_id, значение - session_id
        self.user_sessions: Dict[str, str] = {}

        # Local artifacts manager
        self.artifacts_manager: Optional[LocalArtifactsManager] = None
        if self.settings.is_artifacts_configured():
            cfg = ArtifactsConfig(
                base_path=self.settings.artifacts_base_path,
                ensure_permissions=self.settings.artifacts_ensure_permissions,
                atomic_writes=self.settings.artifacts_atomic_writes,
                max_file_size=self.settings.artifacts_max_file_size,
            )
            self.artifacts_manager = LocalArtifactsManager(cfg)

        # хранилище пользовательских настроек
        self.user_settings: Dict[str, Dict[str, Any]] = {}

        # хранилище артефактов данных по thread_id
        self.artifacts_data: Dict[str, Dict[str, Any]] = {}

    # ---------- internal helpers ----------

    async def _ensure_setup(self):
        """Инициализация БД чекпоинтов"""
        if self._setup_done:
            return
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            await saver.setup()
        self._setup_done = True
        logger.info("PostgreSQL checkpointer setup completed")

    async def _get_state(self, thread_id: str):
        """Получение состояния для thread_id"""
        await self._ensure_setup()
        cfg = {"configurable": {"thread_id": thread_id}}
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            return await graph.aget_state(cfg)

    async def _update_state(self, thread_id: str, update: Dict[str, Any]):
        """Обновление состояния для thread_id"""
        await self._ensure_setup()
        cfg = {"configurable": {"thread_id": thread_id}}
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            await graph.aupdate_state(cfg, update)

    async def delete_thread(self, thread_id: str):
        """Удаление thread и всех связанных данных"""
        await self._ensure_setup()
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            await saver.adelete_thread(thread_id)

        # Очищаем артефакты данные из словаря
        if thread_id in self.artifacts_data:
            del self.artifacts_data[thread_id]

        # Также удаляем session_id для этого пользователя
        self.delete_session(thread_id)

        logger.info(f"Thread {thread_id} deleted successfully")

    # ---------- langfuse session management ----------

    def create_new_session(self, thread_id: str) -> str:
        """
        Создает новый session_id для пользователя.

        Args:
            thread_id: Идентификатор потока

        Returns:
            str: Новый session_id
        """
        session_id = str(uuid.uuid4())
        self.user_sessions[thread_id] = session_id
        logger.info(f"Created new session '{session_id}' for user {thread_id}")
        return session_id

    def get_session_id(self, thread_id: str) -> Optional[str]:
        """
        Получает текущий session_id для пользователя.

        Args:
            thread_id: Идентификатор потока

        Returns:
            Optional[str]: session_id или None, если сессии нет
        """
        return self.user_sessions.get(thread_id)

    def delete_session(self, thread_id: str) -> None:
        """
        Удаляет session_id для пользователя.

        Args:
            thread_id: Идентификатор потока
        """
        if thread_id in self.user_sessions:
            session_id = self.user_sessions.pop(thread_id)
            logger.info(f"Deleted session '{session_id}' for user {thread_id}")

    # ---------- local artifacts management ----------

    async def _push_complete_materials_to_artifacts(
        self, thread_id: str, state_vals: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Пушит все материалы в локальное хранилище в конце workflow.
        Работает корректно как с изображениями/синтезом, так и без них.

        Args:
            thread_id: Идентификатор потока
            state_vals: Значения состояния графа

        Returns:
            Словарь с данными для обновления состояния или None
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping complete materials push"
            )
            return None

        try:
            # Извлекаем все материалы из состояния
            exam_question = state_vals.get("exam_question", "")
            generated_material = state_vals.get("generated_material", "")
            recognized_notes = state_vals.get("recognized_notes", "")
            synthesized_material = state_vals.get("synthesized_material", "")
            image_paths = state_vals.get("image_paths", [])
            gap_questions = state_vals.get("gap_questions", [])
            gap_q_n_a = state_vals.get("gap_q_n_a", [])

            # Подготавливаем данные для комплексного пуша
            all_materials = {
                "generated_material": generated_material,
                "recognized_notes": recognized_notes,
                "synthesized_material": synthesized_material,
                "image_paths": image_paths,
                "gap_questions": gap_questions,
                "gap_q_n_a": gap_q_n_a,
            }

            # Используем комплексный метод Artifacts manager
            result = await self.artifacts_manager.push_complete_materials(
                thread_id=thread_id,
                exam_question=exam_question,
                all_materials=all_materials,
            )

            if result.get("success"):
                logger.info(
                    f"Successfully pushed complete materials for thread {thread_id} to local storage"
                )

                # Обновляем данные в словаре GraphManager
                if thread_id not in self.artifacts_data:
                    self.artifacts_data[thread_id] = {}
                self.artifacts_data[thread_id].update(
                    {
                        "local_session_path": result.get("folder_path"),
                        "local_folder_path": result.get("folder_path"),
                    }
                )

                return result
            else:
                logger.error(
                    f"Failed to push complete materials for thread {thread_id}: {result.get('error')}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Error pushing complete materials to local storage for thread {thread_id}: {e}"
            )
            return None


    async def process_step(self, thread_id: str, query: str, image_paths: List[str] = None) -> Dict[str, Any]:
        """
        Упрощенный главный метод для обработки шагов workflow.
        
        Args:
            thread_id: Идентификатор потока
            query: Текстовый запрос или команда
            image_paths: Опциональный список путей к изображениям
            
        Returns:
            Результат обработки с thread_id и сообщениями
        """
        # 1. Подготовка
        thread_id, input_state, cfg = await self._prepare_workflow(
            thread_id, query, image_paths
        )
        
        # 2. Выполнение workflow
        await self._run_workflow(thread_id, input_state, cfg)
        
        # 3. Финализация
        return await self._finalize_workflow(thread_id)

    async def get_current_step(self, thread_id: str) -> Dict[str, str]:
        """Получение текущего шага workflow"""
        state = await self._get_state(thread_id)
        node = None
        if state and state.interrupts:
            node = state.interrupts[0].ns[0].split(":")[0]

        current_step = {
            "node": node,
            "description": NODE_DESCRIPTIONS.get(node, NODE_DESCRIPTIONS[None]),
        }
        logger.debug(f"Current step for thread {thread_id}: {current_step}")
        return current_step

    async def get_thread_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """Получение полного состояния thread'а"""
        try:
            state = await self._get_state(thread_id)
            if state and state.values:
                return state.values
            return None
        except Exception as e:
            logger.error(f"Error getting state for thread {thread_id}: {str(e)}")
            return None

    # ---------- New refactored methods ----------

    async def _prepare_workflow(
        self, thread_id: str, query: str, image_paths: Optional[List[str]]
    ) -> Tuple[str, Any, Dict[str, Any]]:
        """
        Подготовка workflow: thread_id, начальное состояние, конфигурация

        Args:
            thread_id: Идентификатор потока
            query: Текстовый запрос
            image_paths: Опциональный список путей к изображениям

        Returns:
            Tuple[thread_id, input_state, config]
        """
        # Генерируем thread_id если не передан
        if not thread_id:
            thread_id = str(uuid.uuid4())
            logger.info(f"Created new thread: {thread_id}")

        # Валидируем image_paths
        image_paths = image_paths or []
        if image_paths:
            logger.info(f"Processing with {len(image_paths)} images for thread {thread_id}")

        state = await self._get_state(thread_id)

        # Определяем input_state и session_id для LangFuse
        if not state.values:  # fresh run - новый workflow
            logger.info(f"Starting fresh run for thread {thread_id}")
            input_state = ExamState(
                exam_question=query,
                image_paths=image_paths  # Добавляем изображения в начальное состояние
            )
            # Создаем новый session_id для нового диалога
            session_id = self.create_new_session(thread_id)
        else:  # continue - продолжение существующего workflow
            logger.info(f"Continuing run for thread {thread_id}")
            
            if image_paths:
                # Добавляем изображения через Command.update
                logger.info(f"Adding {len(image_paths)} images to existing workflow")
                input_state = Command(
                    resume=query,
                    update={"image_paths": image_paths}
                )
            else:
                # Обычное продолжение без изображений
                input_state = Command(resume=query)
            
            # Используем существующий session_id
            session_id = self.get_session_id(thread_id) or self.create_new_session(thread_id)

        # Конфигурация с LangFuse трассировкой
        cfg = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [self.langfuse_handler],
            "metadata": {
                "langfuse_session_id": session_id,
                "langfuse_user_id": thread_id
            },
        }

        return thread_id, input_state, cfg

    async def _run_workflow(
        self, thread_id: str, input_state: Any, cfg: Dict[str, Any]
    ) -> None:
        """
        Запуск workflow и обработка событий

        Args:
            thread_id: Идентификатор потока
            input_state: Начальное состояние или команда
            cfg: Конфигурация запуска
        """
        await self._ensure_setup()
        
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            
            async for event in graph.astream(input_state, cfg, stream_mode="updates"):
                await self._handle_workflow_event(event, thread_id)

    async def _handle_workflow_event(self, event: Dict, thread_id: str) -> None:
        """
        Обработка одного события workflow

        Args:
            event: Событие от графа
            thread_id: Идентификатор потока
        """
        logger.debug(f"Event: {event}")
        
        for node_name, node_data in event.items():
            await self._process_node_artifacts(node_name, node_data, thread_id)

    async def _process_node_artifacts(
        self, node_name: str, node_data: Dict, thread_id: str
    ) -> None:
        """
        Универсальная обработка артефактов для узла

        Args:
            node_name: Имя узла
            node_data: Данные узла
            thread_id: Идентификатор потока
        """
        config = self.NODE_ARTIFACT_CONFIG.get(node_name)
        if not config:
            return
        
        # Получаем текущее состояние
        state = await self._get_state(thread_id)
        
        # Проверяем условие сохранения
        if not config["condition"](node_data, state.values):
            return
        
        logger.info(f"Saving artifacts for {node_name}, thread {thread_id}")
        
        # Вызываем соответствующий обработчик
        handler = getattr(self, config["handler"])
        await handler(thread_id, node_data, state.values)

    async def _finalize_workflow(self, thread_id: str) -> Dict[str, Any]:
        """
        Завершение workflow: обработка прерываний или финальная очистка

        Args:
            thread_id: Идентификатор потока

        Returns:
            Dict с результатом выполнения
        """
        final_state = await self._get_state(thread_id)

        logger.debug(f"final_state interrupts: {final_state.interrupts}")

        if final_state.interrupts:
            interrupt_data = final_state.interrupts[0].value
            logger.debug(f"Interrupt data: {interrupt_data}")
            msgs = interrupt_data.get("message", [str(interrupt_data)])

            # Добавляем ссылку на обучающий материал, если это первый interrupt после generating_questions
            learning_material_link_sent = self.artifacts_data.get(thread_id, {}).get(
                "learning_material_link_sent", False
            )
            logger.debug(f"learning_material_link_sent: {learning_material_link_sent}")
            if not learning_material_link_sent:
                learning_material_path = self.artifacts_data.get(thread_id, {}).get(
                    "local_learning_material_path"
                )
                logger.debug(f"learning_material_path: {learning_material_path}")
                if learning_material_path:
                    logger.debug(f"final_state.next: {final_state.next}")
                    msgs.append(
                        f"📚 Обучающий материал сохранён: {learning_material_path}"
                    )
                    # Помечаем, что ссылка уже отправлена
                    if thread_id not in self.artifacts_data:
                        self.artifacts_data[thread_id] = {}
                    self.artifacts_data[thread_id]["learning_material_link_sent"] = True
                    logger.debug(
                        f"Marked learning_material_link_sent=True for thread {thread_id}"
                    )

            logger.info(f"Workflow interrupted for thread {thread_id}")
            return {"thread_id": thread_id, "result": msgs}

        # happy path – всё закончено
        logger.info(f"Workflow completed for thread {thread_id}")

        # Пуш всех материалов в GitHub перед удалением thread
        final_state_values = final_state.values if final_state else {}
        await self._push_complete_materials_to_artifacts(thread_id, final_state_values)

        # Формируем финальное сообщение со ссылкой на GitHub директорию (до удаления thread'а)
        final_message = ["Готово 🎉 – присылайте следующий экзаменационный вопрос!"]

        local_folder_path = self.artifacts_data.get(thread_id, {}).get(
            "local_folder_path"
        )
        if local_folder_path:
            final_message.append(
                f"📁 Все материалы сохранены: {local_folder_path}\n\nПрисылайте следующий экзаменационный вопрос!"
            )

        await self.delete_thread(thread_id)

        return_data = {"thread_id": thread_id, "result": final_message}
        logger.debug(f"return_data: {return_data}")

        return return_data

    # ---------- Специализированные методы сохранения артефактов ----------

    async def _save_learning_material(
        self, thread_id: str, node_data: Dict, state_values: Dict
    ) -> None:
        """
        Создает новую сессию и сохраняет обучающий материал

        Args:
            thread_id: Идентификатор потока
            node_data: Данные от узла
            state_values: Текущие значения состояния графа
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping learning material save"
            )
            return
        
        result = await self.artifacts_manager.push_learning_material(
            thread_id=thread_id,
            exam_question=state_values.get("exam_question", ""),
            generated_material=node_data.get("generated_material", ""),
            display_name=state_values.get("display_name")
        )
        
        if result.get("success"):
            logger.info(
                f"Successfully saved learning material for thread {thread_id}: {result.get('file_path')}"
            )
            
            # Сохраняем пути в локальном словаре
            if thread_id not in self.artifacts_data:
                self.artifacts_data[thread_id] = {}
            
            self.artifacts_data[thread_id].update({
                "local_session_path": result.get("folder_path"),
                "local_folder_path": result.get("folder_path"),
                "session_id": result.get("session_id"),
                "local_learning_material_path": result.get("file_path")
            })
            
            # Обновляем состояние графа
            await self._update_state(thread_id, self.artifacts_data[thread_id])
        else:
            logger.error(
                f"Failed to save learning material for thread {thread_id}: {result.get('error')}"
            )

    async def _save_recognized_notes(
        self, thread_id: str, node_data: Dict, state_values: Dict
    ) -> None:
        """
        Сохраняет распознанные конспекты в существующую сессию

        Args:
            thread_id: Идентификатор потока
            node_data: Данные от узла
            state_values: Текущие значения состояния графа
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping recognized notes save"
            )
            return
            
        folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
        if not folder_path:
            logger.warning(f"No folder path for thread {thread_id}, skipping recognized notes save")
            return
        
        try:
            await self.artifacts_manager.push_recognized_notes(
                folder_path=folder_path,
                recognized_notes=node_data.get("recognized_notes", ""),
                thread_id=thread_id
            )
            logger.info(f"Successfully saved recognized notes for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to save recognized notes for thread {thread_id}: {e}")

    async def _save_synthesized_material(
        self, thread_id: str, node_data: Dict, state_values: Dict
    ) -> None:
        """
        Сохраняет или перезаписывает синтезированный материал

        Args:
            thread_id: Идентификатор потока
            node_data: Данные от узла
            state_values: Текущие значения состояния графа
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping synthesized material save"
            )
            return
            
        folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
        if not folder_path:
            logger.warning(f"No folder path for thread {thread_id}, skipping synthesized material save")
            return
        
        # Для edit_material берем из состояния, для synthesis_material из node_data
        is_edit_node = node_data.get("last_action") == "edit"
        material = (state_values.get("synthesized_material") 
                    if is_edit_node
                    else node_data.get("synthesized_material", ""))
        
        if not material:
            logger.warning(f"No synthesized material to save for thread {thread_id}")
            return
        
        try:
            await self.artifacts_manager.push_synthesized_material(
                folder_path=folder_path,
                synthesized_material=material,
                thread_id=thread_id
            )
            action = "edited" if is_edit_node else "synthesized"
            logger.info(f"Successfully saved {action} material for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to save synthesized material for thread {thread_id}: {e}")

    async def _save_gap_questions(
        self, thread_id: str, node_data: Dict, state_values: Dict
    ) -> None:
        """
        Сохраняет gap questions

        Args:
            thread_id: Идентификатор потока
            node_data: Данные от узла
            state_values: Текущие значения состояния графа
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping gap questions save"
            )
            return
            
        folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
        if not folder_path:
            logger.warning(f"No folder path for thread {thread_id}, skipping gap questions save")
            return
        
        gap_questions = node_data.get("gap_questions", [])
        if not gap_questions:
            logger.warning(f"No gap questions to save for thread {thread_id}")
            return
        
        try:
            # Сохраняем только вопросы без ответов
            await self.artifacts_manager.push_questions_and_answers(
                folder_path=folder_path,
                gap_questions=gap_questions,
                gap_q_n_a=[],  # Пустой список, т.к. ответов еще нет
                thread_id=thread_id
            )
            logger.info(f"Successfully saved gap questions for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to save gap questions for thread {thread_id}: {e}")

    async def _save_answers(
        self, thread_id: str, node_data: Dict, state_values: Dict
    ) -> None:
        """
        Сохраняет ответы на вопросы

        Args:
            thread_id: Идентификатор потока
            node_data: Данные от узла
            state_values: Текущие значения состояния графа
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping answers save"
            )
            return
            
        folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
        if not folder_path:
            logger.warning(f"No folder path for thread {thread_id}, skipping answers save")
            return
        
        gap_q_n_a = state_values.get("gap_q_n_a", [])
        if not gap_q_n_a:
            logger.warning(f"No answers to save for thread {thread_id}")
            return
        
        try:
            # Обновляем файл с вопросами и ответами
            await self.artifacts_manager.push_questions_and_answers(
                folder_path=folder_path,
                gap_questions=state_values.get("gap_questions", []),
                gap_q_n_a=gap_q_n_a,
                thread_id=thread_id
            )
            logger.info(f"Successfully saved answers for thread {thread_id}")
        except Exception as e:
            logger.error(f"Failed to save answers for thread {thread_id}: {e}")
