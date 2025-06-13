"""
Узел генерации вопросов с HITL логикой.
Адаптирован из generating_questions_node в main.ipynb с использованием FeedbackNode паттерна.
"""

import json
import logging
from typing import Dict, Any, Literal
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langfuse.langchain import CallbackHandler
from langgraph.constants import Send
from langgraph.types import Command

from .base import FeedbackNode
from ..state import ExamState, GapQuestions, GapQuestionsHITL
from ..settings import get_settings
from ..utils import get_prompt_template, Config, pretty_print_pydantic


logger = logging.getLogger(__name__)


class QuestionGenerationNode(FeedbackNode):
    """
    Узел генерации gap questions с HITL циклом.
    Использует FeedbackNode паттерн для взаимодействия с пользователем.
    """
    
    def __init__(self):
        super().__init__(logger)
        self.settings = get_settings()
        self.config = Config()
        self.langfuse_handler = CallbackHandler()
        
        # Инициализация модели с LangFuse
        self.model = ChatOpenAI(
            model=self.settings.model_name,
            temperature=self.settings.temperature,
            openai_api_key=self.settings.openai_api_key,
            callbacks=[self.langfuse_handler]
        )

    def is_initial(self, state: ExamState) -> bool:
        """Проверяет, нужно ли делать первую генерацию"""
        return not state.feedback_messages

    def get_template_type(self) -> str:
        """Возвращает тип шаблона для промпта"""
        return "gen_question"

    def get_prompt_kwargs(self, state: ExamState, user_feedback: str = None, config=None) -> Dict[str, Any]:
        """Возвращает параметры для промпта в зависимости от варианта"""
        if user_feedback is None:
            # Первичная генерация (initial variant)
            self._current_stage = "initial"
            return {
                "exam_question": state.exam_question,
                "study_material": state.generated_material,
                "json_schema": pretty_print_pydantic(GapQuestions)
            }
        else:
            # Уточнение на основе feedback (further variant)
            self._current_stage = "refine"
            return {
                "exam_question": state.exam_question,
                "study_material": state.generated_material,
                "current_questions": state.gap_questions,
                "json_schema": pretty_print_pydantic(GapQuestionsHITL)
            }

    def get_model(self):
        """Возвращает модель для генерации с structured output"""
        # Используем staged logic из get_prompt_kwargs
        if hasattr(self, '_current_stage') and self._current_stage == "refine":
            return self.model.with_structured_output(GapQuestionsHITL)
        return self.model.with_structured_output(GapQuestions)

    def format_initial_response(self, response) -> str:
        """Форматирует ответ для отображения пользователю"""
        questions = response.gap_questions
        # Форматируем вопросы как нумерованный список
        return "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])

    def is_approved(self, response: GapQuestionsHITL) -> bool:
        """Проверяет, готовы ли вопросы к финализации"""
        return response.next_step == "finalize"

    def get_next_node(self, state: ExamState, approved: bool = False) -> str:
        """Определяет следующий узел"""
        if approved:
            # Возвращаем список параллельных задач
            return [Send("answer_question", {"question": question}) 
                   for question in state.gap_questions]
        return "generating_questions"

    def get_user_prompt(self) -> str:
        """Возвращает промпт для пользователя"""
        return "Оцените предложенные вопросы. Вы можете запросить изменения или подтвердить, что вопросы готовы к использованию."

    def get_update_on_approve(self, state: ExamState, response) -> Dict[str, Any]:
        """Обновление состояния при одобрении"""
        return {
            "gap_questions": response.gap_questions,
            "feedback_messages": [],  # Очищаем историю feedback
        }

    def get_current_node_name(self) -> str:
        """Имя текущего узла"""
        return "generating_questions"

    def get_initial_update(self, response) -> Dict[str, Any]:
        """Переопределяем для сохранения gap_questions в состоянии"""
        formatted = self.format_initial_response(response)
        return {
            "gap_questions": response.gap_questions,
            "feedback_messages": [AIMessage(content=formatted)]
        }

    def get_continue_update(self, state, user_feedback: str, response) -> Dict[str, Any]:
        """Переопределяем для обновления gap_questions"""
        self.logger.debug(f"User feedback: {user_feedback}")
        self.logger.debug(f"Response: {response}")
        formatted = self.format_initial_response(response)
        self.logger.debug(f"Formatted: {formatted}")
        return {
            "gap_questions": response.gap_questions,
            "feedback_messages": state.feedback_messages + [
                HumanMessage(content=user_feedback),
                AIMessage(content=formatted),
            ]
        } 