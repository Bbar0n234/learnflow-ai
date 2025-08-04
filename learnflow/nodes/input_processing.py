"""
Узел обработки пользовательского ввода.
Анализирует входящие данные и определяет наличие изображений.
"""

import logging
from typing import Literal
from langgraph.types import Command
from pathlib import Path

from ..state import ExamState
from ..file_utils import ImageFileManager
from .base import BaseWorkflowNode


logger = logging.getLogger(__name__)


class InputProcessingNode(BaseWorkflowNode):
    """
    Узел обработки пользовательского ввода.
    Анализирует message и image_paths, устанавливает правильные значения состояния.
    Простой узел без HITL логики.
    """
    
    def __init__(self):
        super().__init__(logger)
        self.file_manager = ImageFileManager()
    
    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "input_processing"

    async def __call__(self, state: ExamState, config) -> Command[Literal["generating_content"]]:
        """
        Обрабатывает пользовательский ввод и валидирует изображения.
        
        Args:
            state: Текущее состояние с exam_question и потенциально image_paths
            config: Конфигурация LangGraph
            
        Returns:
            Command с переходом к генерации контента и обновленным состоянием
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting input processing for thread {thread_id}")
        
        # Извлекаем экзаменационный вопрос из message (если он был передан через message)
        exam_question = state.exam_question.strip()
        if not exam_question:
            logger.error(f"Empty exam question for thread {thread_id}")
            raise ValueError("Экзаменационный вопрос не может быть пустым")
        
        # Валидируем и обрабатываем изображения
        validated_image_paths = []
        if state.image_paths:
            logger.info(f"Found {len(state.image_paths)} image paths to validate")
            
            for image_path in state.image_paths:
                path_obj = Path(image_path)
                if path_obj.exists() and self.file_manager.validate_image_file(path_obj):
                    validated_image_paths.append(image_path)
                    logger.info(f"Validated image: {image_path}")
                else:
                    logger.warning(f"Invalid or missing image: {image_path}")
        
        # Обновляем состояние
        update_data = {
            "exam_question": exam_question,
            "image_paths": validated_image_paths
        }
        
        logger.info(f"Input processing completed for thread {thread_id}. "
                   f"Question: '{exam_question[:100]}...', Images: {len(validated_image_paths)}")
        
        return Command(
            goto="generating_content",
            update=update_data
        ) 