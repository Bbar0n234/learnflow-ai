"""
Узел обработки пользовательского ввода.
Анализирует входящие данные и определяет наличие изображений.
"""

import logging
from typing import Literal
from langgraph.types import Command
from pathlib import Path

from ..core.state import GeneralState
from ..services.file_utils import ImageFileManager
from .base import BaseWorkflowNode


logger = logging.getLogger(__name__)


class InputProcessingNode(BaseWorkflowNode):
    """
    Узел обработки пользовательского ввода.
    Анализирует message и image_paths, устанавливает правильные значения состояния.
    Простой узел без HITL логики.
    """

    def __init__(self):
        super().__init__(logger=logger)
        self.file_manager = ImageFileManager()

    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "input_processing"

    async def __call__(
        self, state: GeneralState, config
    ) -> Command[Literal["generating_content"]]:
        """
        Обрабатывает пользовательский ввод и валидирует изображения.

        Args:
            state: Текущее состояние с input_content и потенциально image_paths
            config: Конфигурация LangGraph

        Returns:
            Command с переходом к генерации контента и обновленным состоянием
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting input processing for thread {thread_id}")

        # Получаем input_content из state
        input_content = state.input_content

        # Валидация input_content на самом входе в систему
        logger.debug(f"Security guard status: {self.security_guard is not None}")
        if self.security_guard:
            logger.info("Validating exam question for security threats")
            input_content = await self.validate_input(input_content)
        else:
            logger.warning("Security guard not initialized - skipping validation")

        # Генерируем краткое название для сессии
        display_name = None
        try:
            model = self.create_model()
            display_name_prompt = f"""Создай краткое название (3-5 слов) для следующего экзаменационного вопроса:
"{input_content}"

Требования:
- Максимум 5 слов
- Отражает суть вопроса
- Без спецсимволов и знаков препинания
- На том же языке, что и вопрос

Ответ дай ТОЛЬКО название, без объяснений."""

            response = await model.ainvoke(display_name_prompt)
            display_name = response.content.strip()
            logger.info(f"Generated display_name: {display_name}")
        except Exception as e:
            logger.warning(f"Failed to generate display_name: {e}")
            # Fallback: используем первые слова вопроса
            words = input_content.split()[:5]
            display_name = " ".join(words)
            if len(words) > 5:
                display_name += "..."

        # Валидируем и обрабатываем изображения
        validated_image_paths = []
        if state.image_paths:
            logger.info(f"Found {len(state.image_paths)} image paths to validate")

            for image_path in state.image_paths:
                path_obj = Path(image_path)
                if path_obj.exists() and self.file_manager.validate_image_file(
                    path_obj
                ):
                    validated_image_paths.append(image_path)
                    logger.info(f"Validated image: {image_path}")
                else:
                    logger.warning(f"Invalid or missing image: {image_path}")

        # Обновляем состояние
        update_data = {
            "input_content": input_content,
            "image_paths": validated_image_paths,
            "display_name": display_name,  # Добавляем display_name в состояние
        }

        logger.info(
            f"Input processing completed for thread {thread_id}. "
            f"Question: '{input_content[:100]}...', Images: {len(validated_image_paths)}"
        )

        return Command(goto="generating_content", update=update_data)
