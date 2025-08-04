"""
Узел генерации обучающего материала.
Адаптирован из generating_content_node в main.ipynb для production архитектуры.
"""
import logging
from typing import Literal, Union
from langchain_core.messages import SystemMessage
from langgraph.types import Command

from ..state import ExamState
from ..utils import render_system_prompt
from .base import BaseWorkflowNode


logger = logging.getLogger(__name__)


class ContentGenerationNode(BaseWorkflowNode):
    """
    Узел генерации обучающего материала на основе экзаменационного вопроса.
    Определяет следующий переход: если есть изображения - в recognition, если нет - в generating_questions.
    """
    
    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()
    
    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "generating_content"
        

    async def __call__(
        self, 
        state: ExamState, 
        config
    ) -> Union[Command[Literal["recognition_handwritten"]], Command[Literal["generating_questions"]]]:
        """
        Генерирует обучающий материал на основе экзаменационного вопроса.
        
        Args:
            state: Текущее состояние с экзаменационным вопросом
            config: Конфигурация LangGraph
            
        Returns:
            Command с переходом к распознаванию изображений или генерации вопросов
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting content generation for thread {thread_id}")
        
        # Формируем промпт
        prompt_content = render_system_prompt(
            template_type='generating_content',
            exam_question=state.exam_question
        )
        
        messages = [SystemMessage(content=prompt_content)]
        
        # Генерируем материал
        logger.debug(f"Generating content for question: {state.exam_question[:100]}...")
        response = await self.model.ainvoke(messages)
        
        logger.info(f"Content generated successfully for thread {thread_id}")
        
        # Определяем следующий узел на основе наличия изображений
        has_images = bool(state.image_paths)
        
        if has_images:
            logger.info(f"Found {len(state.image_paths)} images, proceeding to recognition")
            next_node = "recognition_handwritten"
        else:
            logger.info(f"No images found, proceeding directly to question generation")
            next_node = "generating_questions"
        
        return Command(
            goto=next_node,
            update={
                "generated_material": response.content,
            }
        )
            