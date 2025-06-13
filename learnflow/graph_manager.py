"""
GraphManager – единая оболочка вокруг LangGraph workflow.
Отвечает за:
• lazy-инициализацию БД чекпоинтов
• запуск / продолжение графа
• передачу сообщений HITL-узлов наружу
• пуш артефактов (опционально) в GitHub

Адаптирован из project_documentation.md для ExamState.
"""

import os
import uuid
import logging
from typing import Dict, Any, Optional

from langgraph.types import Command
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from .graph import create_workflow
from .state import ExamState
from .settings import get_settings
from .github import GitHubArtifactPusher, GitHubConfig


NODE_DESCRIPTIONS = {
    "generating_content":    "Генерация обучающего материала",
    "generating_questions":  "Генерация и правка gap questions",
    "answer_question":       "Генерация ответов на вопросы",
    None:                    "Готов к новому экзаменационному вопросу",
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
        if self.settings.is_github_configured():
            cfg = GitHubConfig(
                token=self.settings.github_token,
                repository=self.settings.github_repository,
                branch=self.settings.github_branch,
                base_path=self.settings.github_base_path,
            )
            self.github_pusher = GitHubArtifactPusher(cfg)

        # хранилище пользовательских настроек
        self.user_settings: Dict[str, Dict[str, Any]] = {}
        
        # хранилище GitHub данных по thread_id
        self.github_data: Dict[str, Dict[str, Any]] = {}

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
        
        # Очищаем GitHub данные из словаря
        if thread_id in self.github_data:
            del self.github_data[thread_id]
            
        logger.info(f"Thread {thread_id} deleted successfully")

    # ---------- github artifacts (отключено для упрощения) ----------

    async def _push_learning_material_to_github(self, thread_id: str, state_vals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Пушит обучающий материал в GitHub после генерации контента.
        
        Args:
            thread_id: Идентификатор потока
            state_vals: Значения состояния графа
            
        Returns:
            Словарь с данными для обновления состояния или None
        """
        if not self.github_pusher:
            logger.debug("GitHub pusher not configured, skipping learning material push")
            return None

        # Проверяем, что есть необходимые данные
        exam_question = state_vals.get('exam_question', '')
        generated_material = state_vals.get('generated_material', '')
        
        if not exam_question or not generated_material:
            logger.warning(f"Missing learning material data for thread {thread_id}, skipping GitHub push")
            return None

        try:
            # Пушим обучающий материал
            result = await self.github_pusher.push_learning_material(
                thread_id=thread_id,
                exam_question=exam_question,
                generated_material=generated_material,
            )
            
            if result.get('success'):
                logger.info(f"Successfully pushed learning material for thread {thread_id} to GitHub: {result.get('file_path')}")
                
                # Данные для обновления состояния
                github_data = {
                    "github_folder_path": result.get("folder_path"),
                    "github_learning_material_url": result.get("learning_material_url"),
                    "github_folder_url": result.get("folder_url")
                }
                
                # Сохраняем данные в словарь GraphManager
                if thread_id not in self.github_data:
                    self.github_data[thread_id] = {}
                self.github_data[thread_id].update(github_data)
                
                return github_data
            else:
                logger.error(f"Failed to push learning material for thread {thread_id}: {result.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error pushing learning material to GitHub for thread {thread_id}: {e}")
            return None
    
    async def _push_questions_to_github(self, thread_id: str, state_vals: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Пушит вопросы и ответы в GitHub перед удалением thread.
        
        Args:
            thread_id: Идентификатор потока
            state_vals: Значения состояния графа
            
        Returns:
            Словарь с данными для обновления состояния или None
        """
        if not self.github_pusher:
            logger.debug("GitHub pusher not configured, skipping questions push")
            return None

        # Проверяем, что есть папка для пуша
        folder_path = state_vals.get('github_folder_path', '')
        if not folder_path:
            logger.warning(f"No GitHub folder path found for thread {thread_id}, skipping questions push")
            return None

        # Извлекаем данные о вопросах и ответах
        gap_questions = state_vals.get('gap_questions', [])
        gap_q_n_a = state_vals.get('gap_q_n_a', [])
        
        if not gap_questions and not gap_q_n_a:
            logger.warning(f"No questions or answers found for thread {thread_id}, skipping GitHub push")
            return None

        try:
            # Пушим вопросы и ответы
            result = await self.github_pusher.push_questions_and_answers(
                folder_path=folder_path,
                gap_questions=gap_questions,
                gap_q_n_a=gap_q_n_a,
                thread_id=thread_id,
            )
            
            if result.get('success'):
                logger.info(f"Successfully pushed questions and answers for thread {thread_id} to GitHub: {result.get('file_path')}")
                
                # Данные для обновления состояния
                github_data = {"github_questions_url": result.get("html_url")}
                
                # Сохраняем данные в словарь GraphManager
                if thread_id not in self.github_data:
                    self.github_data[thread_id] = {}
                self.github_data[thread_id].update(github_data)
                
                return github_data
            else:
                logger.error(f"Failed to push questions and answers for thread {thread_id}: {result.get('error')}")
                return None
                
        except Exception as e:
            logger.error(f"Error pushing questions and answers to GitHub for thread {thread_id}: {e}")
            return None

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
            logger.info(f"Created new thread: {thread_id}")

        state = await self._get_state(thread_id)
        cfg = {"configurable": {"thread_id": thread_id}}

        # определяем input_state
        if not state.values:                           # fresh run
            logger.info(f"Starting fresh run for thread {thread_id}")
            input_state = ExamState(exam_question=query)
        else:                                          # continue
            logger.info(f"Continuing run for thread {thread_id}")
            input_state = Command(resume=query)

        # запускаем/продолжаем граф
        await self._ensure_setup()
        async with AsyncPostgresSaver.from_conn_string(
            self.settings.database_url
        ) as saver:
            graph = self.workflow.compile(checkpointer=saver)
            
            async for event in graph.astream(
                input_state, cfg, stream_mode="updates"
            ):
                # HITL сообщения наружу
                logger.debug(f"Event: {event}")
                
                updated_state = await self._get_state(thread_id)

                logger.debug(f"updated github_folder_path: {updated_state.values.get('github_folder_path')}")
                logger.debug(f"updated github_learning_material_url: {updated_state.values.get('github_learning_material_url')}")
                logger.debug(f"updated github_folder_url: {updated_state.values.get('github_folder_url')}")
                
                for node_name, node_data in event.items():
                    logger.debug(f"Node: {node_name}, Data type: {type(node_data)}, Data: {node_data}")
                    
                    # Пуш обучающего материала после завершения generating_content
                    if node_name == "generating_content":
                        logger.info(f"Content generation completed for thread {thread_id}, pushing to GitHub...")
                        current_state = await self._get_state(thread_id)
                        github_data = await self._push_learning_material_to_github(thread_id, current_state.values)
                        if github_data:
                            await self._update_state(thread_id, github_data)

        # после завершения / остановки
        final_state = await self._get_state(thread_id)
        if final_state.interrupts:
            interrupt_data = final_state.interrupts[0].value
            logger.debug(f"Interrupt data: {interrupt_data}")
            msgs = interrupt_data.get("message", [str(interrupt_data)])
            
            # Добавляем ссылку на обучающий материал, если это первый interrupt после generating_questions

            logger.debug(f"learning_material_link_sent: {final_state.values.get('learning_material_link_sent')}")
            if not final_state.values.get("learning_material_link_sent"):
                learning_material_url = self.github_data.get(thread_id, {}).get("github_learning_material_url")
                logger.debug(f"learning_material_url: {learning_material_url}")
                if learning_material_url:
                    msgs.append(f"📚 Обучающий материал доступен: {learning_material_url}")
                    await self._update_state(thread_id, {"learning_material_link_sent": True})
            
            logger.info(f"Workflow interrupted for thread {thread_id}")
            return {"thread_id": thread_id, "result": msgs}

        # happy path – всё закончено
        logger.info(f"Workflow completed for thread {thread_id}")

        # Пуш вопросов и ответов в GitHub перед удалением thread
        final_state_values = final_state.values if final_state else {}
        questions_github_data = await self._push_questions_to_github(thread_id, final_state_values)
        if questions_github_data:
            await self._update_state(thread_id, questions_github_data)

        # Формируем финальное сообщение со ссылкой на GitHub директорию (до удаления thread'а)
        final_message = "Готово 🎉 – присылайте следующий экзаменационный вопрос!"
        
        github_folder_url = self.github_data.get(thread_id, {}).get("github_folder_url")
        if github_folder_url:
            final_message = f"Готово 🎉\n\n📁 Все материалы сохранены: {github_folder_url}\n\nПрисылайте следующий экзаменационный вопрос!"

        await self.delete_thread(thread_id)
        logger.info(f"Thread {thread_id} deleted successfully")

        return {
            "thread_id": thread_id,
            "result": final_message
        }

    async def get_current_step(self, thread_id: str) -> Dict[str, str]:
        """Получение текущего шага workflow"""
        state = await self._get_state(thread_id)
        node = None
        if state and state.interrupts:
            node = state.interrupts[0].ns[0].split(':')[0]
        
        current_step = {
            "node": node,
            "description": NODE_DESCRIPTIONS.get(node, NODE_DESCRIPTIONS[None])
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