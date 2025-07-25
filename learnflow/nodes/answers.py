"""
Узел генерации ответов на gap questions.
Адаптирован из answer_question_node в main.ipynb для параллельной обработки.
"""

import logging
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command

from ..state import ExamState
from ..settings import get_settings
from ..utils import get_prompt_template, Config


logger = logging.getLogger(__name__)


class AnswerGenerationNode:
    """
    Узел для генерации ответов на отдельные gap questions.
    Используется в параллельных задачах через Send.
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
        self.prompt_template = get_prompt_template('gen_answer_system_prompt', self.config)

    async def __call__(self, data: Dict[str, Any], config=None) -> Command[Literal["__end__"]]:
        """
        Генерирует ответ на один gap question.
        
        Args:
            data: Словарь с ключом 'question' содержащий вопрос для обработки
            config: Конфигурация LangGraph (опционально)
            
        Returns:
            Command с переходом к завершению и сгенерированным Q&A
        """
        question = data.get('question', '')
        
        if config and "configurable" in config:
            thread_id = config["configurable"].get("thread_id", "unknown")
        else:
            thread_id = "unknown"
            
        logger.info(f"Generating answer for question in thread {thread_id}: {question[:100]}...")
        
        try:
            # Формируем промпт для генерации ответа
            prompt_content = self.prompt_template.render(
                exam_question=question
            )
            
            messages = [SystemMessage(content=prompt_content)]
            
            # Генерируем ответ
            response = await self.model.ainvoke(messages)
            
            # Форматируем Q&A для добавления в состояние
            formatted_qna = f"## {question}\n\n{response.content}"
            
            logger.info(f"Answer generated successfully for question in thread {thread_id}")
            
            return Command(
                goto="__end__",
                update={
                    "gap_q_n_a": [formatted_qna],
                }
            )
            
        except Exception as e:
            logger.error(f"Error generating answer for question in thread {thread_id}: {str(e)}")
            # В случае ошибки все равно завершаем, но с error сообщением
            error_qna = f"## {question}\n\n**Ошибка генерации ответа:** {str(e)}"
            return Command(
                goto="__end__",
                update={
                    "gap_q_n_a": [error_qna],
                }
            ) 