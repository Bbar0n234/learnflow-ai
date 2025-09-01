"""
Узел генерации обучающего материала.
Адаптирован из generating_content_node в main.ipynb для production архитектуры.
"""

import logging
from typing import Literal, Union
from langchain_core.messages import SystemMessage
from langgraph.types import Command

from ..core.state import GeneralState
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
    
    def _build_context_from_state(self, state) -> dict:
        """Строит контекст для промпта из состояния workflow"""
        return {
            "input_content": state.input_content if hasattr(state, 'input_content') else "",
            "input_content": state.input_content if hasattr(state, 'input_content') else ""
        }

    async def __call__(
        self, state: GeneralState, config
    ) -> Union[
        Command[Literal["recognition_handwritten"]],
        Command[Literal["generating_questions"]],
    ]:
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

        # Получаем персонализированный промпт от сервиса
        prompt_content = await self.get_system_prompt(state, config)

        messages = [SystemMessage(content=prompt_content)]

        # Генерируем материал
        logger.debug(f"Generating content for question: {state.input_content[:100]}...")
        response = await self.model.ainvoke(messages)

        logger.info(f"Content generated successfully for thread {thread_id}")

        return Command(
            goto="recognition_handwritten",
            update={
                "generated_material": response.content,
            },
        )
