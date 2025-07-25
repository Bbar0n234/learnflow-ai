"""
Узел генерации обучающего материала.
Адаптирован из generating_content_node в main.ipynb для production архитектуры.
"""

import json
import logging
from typing import Literal
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command

from ..state import ExamState
from ..settings import get_settings
from ..utils import get_prompt_template, Config


logger = logging.getLogger(__name__)


class ContentGenerationNode:
    """
    Узел генерации обучающего материала на основе экзаменационного вопроса.
    Без HITL - прямой переход к следующему узлу.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.config = Config()
        
        # Инициализация модели с LangFuse
        self.model = ChatOpenAI(
            model=self.settings.model_name,
            temperature=self.settings.temperature,
            openai_api_key=self.settings.openai_api_key,
        )
        
        # Загрузка шаблона промпта
        self.prompt_template = get_prompt_template('generating_content_system_prompt', self.config)
        




    async def __call__(self, state: ExamState, config) -> Command[Literal["generating_questions"]]:
        """
        Генерирует обучающий материал на основе экзаменационного вопроса.
        
        Args:
            state: Текущее состояние с экзаменационным вопросом
            config: Конфигурация LangGraph
            
        Returns:
            Command с переходом к генерации вопросов и обновленным состоянием
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting content generation for thread {thread_id}")
        
        # Формируем промпт
        prompt_content = self.prompt_template.render(
            exam_question=state.exam_question
        )
        
        messages = [SystemMessage(content=prompt_content)]
        
        # Генерируем материал
        logger.debug(f"Generating content for question: {state.exam_question[:100]}...")
        response = await self.model.ainvoke(messages)
        
        logger.info(f"Content generated successfully for thread {thread_id}")
        
        return Command(
            goto="generating_questions",
            update={
                "generated_material": response.content,
            }
        )
            