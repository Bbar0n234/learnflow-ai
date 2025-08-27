"""
GraphManager – единая оболочка вокруг LangGraph workflow.
Отвечает за:
• lazy-инициализацию БД чекпоинтов
• запуск / продолжение графа
• передачу сообщений HITL-узлов наружу
• пуш артефактов (опционально) в GitHub
• трассировку в LangFuse
Адаптирован из project_documentation.md для ExamState.
"""

import uuid
import logging
from typing import Dict, Any, Optional, List

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

    async def _push_learning_material_to_artifacts(
        self, thread_id: str, state_vals: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Пушит обучающий материал в локальное хранилище после генерации контента.

        Args:
            thread_id: Идентификатор потока
            state_vals: Значения состояния графа

        Returns:
            Словарь с данными для обновления состояния или None
        """
        if not self.artifacts_manager:
            logger.debug(
                "Artifacts manager not configured, skipping learning material push"
            )
            return None

        # Проверяем, что есть необходимые данные
        exam_question = state_vals.get("exam_question", "")
        generated_material = state_vals.get("generated_material", "")
        display_name = state_vals.get(
            "display_name"
        )  # Получаем display_name из состояния

        if not exam_question or not generated_material:
            logger.warning(
                f"Missing learning material data for thread {thread_id}, skipping GitHub push"
            )
            return None

        try:
            # Пушим обучающий материал
            result = await self.artifacts_manager.push_learning_material(
                thread_id=thread_id,
                exam_question=exam_question,
                generated_material=generated_material,
                display_name=display_name,
            )

            if result.get("success"):
                logger.info(
                    f"Successfully pushed learning material for thread {thread_id} to local storage: {result.get('file_path')}"
                )

                # Данные для обновления состояния
                artifacts_data = {
                    "local_session_path": result.get("folder_path"),
                    "local_thread_path": result.get("thread_path"),
                    "session_id": result.get("session_id"),
                    "local_learning_material_path": result.get("file_path"),
                    "local_folder_path": result.get("folder_path"),
                }

                # Сохраняем данные в словарь GraphManager
                if thread_id not in self.artifacts_data:
                    self.artifacts_data[thread_id] = {}
                self.artifacts_data[thread_id].update(artifacts_data)

                return artifacts_data
            else:
                logger.error(
                    f"Failed to push learning material for thread {thread_id}: {result.get('error')}"
                )
                return None

        except Exception as e:
            logger.error(
                f"Error pushing learning material to local storage for thread {thread_id}: {e}"
            )
            return None

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

    async def _push_questions_to_artifacts(
        self, thread_id: str, state_vals: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Пушит вопросы и ответы в локальное хранилище перед удалением thread.
        DEPRECATED: Теперь используется _push_complete_materials_to_artifacts

        Args:
            thread_id: Идентификатор потока
            state_vals: Значения состояния графа

        Returns:
            Словарь с данными для обновления состояния или None
        """
        # Используем комплексный метод вместо отдельного пуша вопросов
        return await self._push_complete_materials_to_artifacts(thread_id, state_vals)

    async def process_step(self, thread_id: str, query: str, image_paths: List[str] = None) -> Dict[str, Any]:
        """
        Универсальный метод для обработки шагов workflow.
        
        Args:
            thread_id: Идентификатор потока
            query: Текстовый запрос или команда
            image_paths: Опциональный список путей к изображениям
            
        Returns:
            Результат обработки с thread_id и сообщениями
        """
        if not thread_id:
            thread_id = str(uuid.uuid4())
            logger.info(f"Created new thread: {thread_id}")
        
        # Валидируем image_paths
        image_paths = image_paths or []
        if image_paths:
            logger.info(f"Processing with {len(image_paths)} images for thread {thread_id}")

        state = await self._get_state(thread_id)

        # определяем input_state и session_id для LangFuse
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
            session_id = self.get_session_id(thread_id) or self.create_new_session(
                thread_id
            )

        # конфигурация с LangFuse трассировкой
        cfg = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [self.langfuse_handler],
            "metadata": {
                "langfuse_session_id": session_id,
                "langfuse_user_id": thread_id
            },
        }

        # запускаем/продолжаем граф
        await self._ensure_setup()
        
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)

            async for event in graph.astream(input_state, cfg, stream_mode="updates"):
                # HITL сообщения наружу
                logger.debug(f"Event: {event}")

                for node_name, node_data in event.items():
                    # Пуш обучающего материала после завершения generating_content
                    if node_name == "generating_content":
                        logger.info(
                            f"Content generation completed for thread {thread_id}, pushing to GitHub..."
                        )
                        current_state = await self._get_state(thread_id)
                        artifacts_data = (
                            await self._push_learning_material_to_artifacts(
                                thread_id,
                                {
                                    "exam_question": current_state.values.get(
                                        "exam_question"
                                    ),
                                    "generated_material": node_data.get(
                                        "generated_material"
                                    ),
                                    "display_name": current_state.values.get(
                                        "display_name"
                                    ),
                                },
                            )
                        )
                        if artifacts_data:
                            await self._update_state(thread_id, artifacts_data)

                    # Пуш синтезированного материала после synthesis_material
                    elif node_name == "synthesis_material" and node_data.get(
                        "synthesized_material"
                    ):
                        logger.info(
                            f"Synthesis completed for thread {thread_id}, pushing to artifacts..."
                        )
                        if self.artifacts_manager:
                            local_folder = self.artifacts_data.get(thread_id, {}).get(
                                "local_folder_path"
                            )
                            if local_folder:
                                try:
                                    await self.artifacts_manager.push_synthesized_material(
                                        folder_path=local_folder,
                                        synthesized_material=node_data.get(
                                            "synthesized_material"
                                        ),
                                        thread_id=thread_id,
                                    )
                                    logger.info(
                                        f"Auto-saved synthesized material to {local_folder}"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to auto-save synthesized material: {e}"
                                    )

                    # Автосохранение после каждой правки в edit_material
                    elif (
                        node_name == "edit_material"
                        and node_data.get("last_action") == "edit"
                    ):
                        logger.info(
                            f"Edit applied in thread {thread_id}, auto-saving to artifacts..."
                        )
                        if self.artifacts_manager:
                            current_state = await self._get_state(thread_id)
                            local_folder = self.artifacts_data.get(thread_id, {}).get(
                                "local_folder_path"
                            )
                            if local_folder and current_state.values.get(
                                "synthesized_material"
                            ):
                                try:
                                    await self.artifacts_manager.push_synthesized_material(
                                        folder_path=local_folder,
                                        synthesized_material=current_state.values.get(
                                            "synthesized_material"
                                        ),
                                        thread_id=thread_id,
                                    )
                                    logger.info(
                                        f"Auto-saved edited material to {local_folder}"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Failed to auto-save edited material: {e}"
                                    )

        # после завершения / остановки
        final_state = await self._get_state(thread_id)

        print(f"final_state interrupts: {final_state.interrupts}")

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
