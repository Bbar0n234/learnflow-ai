"""
Узел генерации ответов на контрольные вопросы.
Адаптирован из answer_question_node в main.ipynb для параллельной обработки.
"""

import logging
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage
from langgraph.types import Command

# from ..utils.utils import render_system_prompt
from .base import BaseWorkflowNode


logger = logging.getLogger(__name__)


class AnswerGenerationNode(BaseWorkflowNode):
    """
    Узел для генерации ответов на отдельные контрольные вопросы.
    Используется в параллельных задачах через Send.
    """

    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()

    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "answer_question"
    
    def _build_context_from_state(self, state) -> dict:
        """Строит контекст для промпта из состояния workflow"""
        # В этом узле state - это dict с ключом 'question'
        if isinstance(state, dict) and 'question' in state:
            return {
                "input_content": state['question']
            }
        return {}

    async def __call__(
        self, data: Dict[str, Any], config=None
    ) -> Command[Literal["__end__"]]:
        """
        Генерирует ответ на один контрольный вопрос.

        Args:
            data: Словарь с ключом 'question' содержащий вопрос для обработки
            config: Конфигурация LangGraph (опционально)

        Returns:
            Command с переходом к завершению и сгенерированным Q&A
        """
        question = data.get("question", "")

        if config and "configurable" in config:
            thread_id = config["configurable"].get("thread_id", "unknown")
        else:
            thread_id = "unknown"

        logger.info(
            f"Generating answer for question in thread {thread_id}: {question[:100]}..."
        )

        try:
            # Создаем псевдо-state с вопросом для передачи в get_system_prompt
            state_dict = {"question": question}
            
            # Получаем персонализированный промпт от сервиса
            prompt_content = await self.get_system_prompt(state_dict, config)

            messages = [SystemMessage(content=prompt_content)]

            # Генерируем ответ
            response = await self.model.ainvoke(messages)

            # Форматируем Q&A для добавления в состояние
            formatted_qna = f"## {question}\n\n{response.content}"

            logger.info(
                f"Answer generated successfully for question in thread {thread_id}"
            )

            return Command(
                goto="__end__",
                update={
                    "questions_and_answers": [formatted_qna],
                },
            )

        except Exception as e:
            logger.error(
                f"Error generating answer for question in thread {thread_id}: {str(e)}"
            )
            # В случае ошибки все равно завершаем, но с error сообщением
            error_qna = f"## {question}\n\n**Ошибка генерации ответа:** {str(e)}"
            return Command(
                goto="__end__",
                update={
                    "questions_and_answers": [error_qna],
                },
            )
