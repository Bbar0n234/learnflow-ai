"""
Узел генерации вопросов с HITL логикой.
Адаптирован из generating_questions_node в main.ipynb с использованием FeedbackNode паттерна.
"""

import logging
from typing import Dict, Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.constants import Send
from langgraph.types import Command
from langchain_core.utils.function_calling import convert_to_openai_function

from .base import FeedbackNode
from ..core.state import GeneralState, Questions, QuestionsHITL
from ..utils.utils import Config
from ..services.hitl_manager import get_hitl_manager


logger = logging.getLogger(__name__)


class QuestionGenerationNode(FeedbackNode):
    """
    Узел генерации gap questions с HITL циклом.
    Использует FeedbackNode паттерн для взаимодействия с пользователем.
    """

    def __init__(self):
        super().__init__(logger)
        self.config = Config()
        self.model = self.create_model()

    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "generating_questions"
    
    def _build_context_from_state(self, state) -> Dict[str, Any]:
        """Строит контекст для промпта из состояния workflow"""
        # FeedbackNode будет использовать prompt_kwargs из get_prompt_kwargs
        # который уже содержит правильный маппинг
        return {}

    def is_initial(self, state: GeneralState) -> bool:
        """Проверяет, нужно ли делать первую генерацию"""
        return not state.feedback_messages

    def get_template_type(self) -> str:
        """Возвращает тип шаблона для промпта"""
        return "gen_question"

    def get_prompt_kwargs(
        self, state: GeneralState, user_feedback: str = None, config=None
    ) -> Dict[str, Any]:
        """Возвращает параметры для промпта в зависимости от варианта"""
        # Используем synthesized_material если есть, иначе generated_material как fallback
        study_material = state.synthesized_material or state.generated_material

        if user_feedback is None:
            # Первичная генерация (initial variant) # TODO: почему Code in unreachable?
            self._current_stage = "initial"
            return {
                "input_content": state.input_content,
                "study_material": study_material,
                "json_schema": convert_to_openai_function(Questions),
            }
        else:
            # Уточнение на основе feedback (further variant)
            self._current_stage = "refine"
            return {
                "input_content": state.input_content,
                "study_material": study_material,
                "current_questions": state.questions,
                "json_schema": convert_to_openai_function(QuestionsHITL),
            }

    def get_model(self):
        """Возвращает модель для генерации с structured output"""
        # Используем staged logic из get_prompt_kwargs
        if hasattr(self, "_current_stage") and self._current_stage == "refine":
            return self.model.with_structured_output(QuestionsHITL)
        return self.model.with_structured_output(Questions)

    def format_initial_response(self, response) -> str:
        """Форматирует ответ для отображения пользователю"""
        questions = response.questions
        # Форматируем вопросы как нумерованный список
        return "\n".join([f"{i + 1}. {q}" for i, q in enumerate(questions)])

    def is_approved(self, response: QuestionsHITL) -> bool:
        """Проверяет, готовы ли вопросы к финализации"""
        return response.next_step == "finalize"

    def get_next_node(self, state: GeneralState, approved: bool = False) -> str:
        """Определяет следующий узел"""
        if approved:
            # Возвращаем список параллельных задач
            return [
                Send("answer_question", {"question": question})
                for question in state.questions
            ]
        return "generating_questions"

    def get_user_prompt(self) -> str:
        """Возвращает промпт для пользователя"""
        return "Оцените предложенные вопросы. Вы можете запросить изменения или подтвердить, что вопросы готовы к использованию."

    def get_update_on_approve(self, state: GeneralState, response) -> Dict[str, Any]:
        """Обновление состояния при одобрении"""
        return {
            "questions": response.questions,
            "feedback_messages": [],  # Очищаем историю feedback
        }

    def get_current_node_name(self) -> str:
        """Имя текущего узла"""
        return "generating_questions"

    def get_initial_update(self, response) -> Dict[str, Any]:
        """Переопределяем для сохранения questions в состоянии"""
        formatted = self.format_initial_response(response)
        return {
            "questions": response.questions,
            "feedback_messages": [AIMessage(content=formatted)],
        }

    def get_continue_update(
        self, state, user_feedback: str, response
    ) -> Dict[str, Any]:
        """Переопределяем для обновления questions"""
        self.logger.debug(f"User feedback: {user_feedback}")
        self.logger.debug(f"Response: {response}")
        formatted = self.format_initial_response(response)
        self.logger.debug(f"Formatted: {formatted}")
        return {
            "questions": response.questions,
            "feedback_messages": state.feedback_messages
            + [
                HumanMessage(content=user_feedback),
                AIMessage(content=formatted),
            ],
        }

    async def __call__(self, state, config) -> Command:
        """Override to check HITL settings before running feedback loop"""
        thread_id = config["configurable"]["thread_id"]
        self.logger.debug(f"Processing QuestionGenerationNode for thread {thread_id}")

        # Check HITL settings
        hitl_manager = get_hitl_manager()
        hitl_enabled = hitl_manager.is_enabled("generating_questions", thread_id)
        self.logger.info(f"HITL for generating_questions: {hitl_enabled}")

        if not hitl_enabled:
            # Run autonomous generation without HITL
            self.logger.info(
                "HITL disabled for generating_questions, running autonomous generation"
            )

            prompt = self.render_prompt(state, config=config)
            model = self.model.with_structured_output(Questions)
            response = await model.ainvoke([SystemMessage(content=prompt)])

            # Move directly to answer generation
            return Command(
                goto=[
                    Send("answer_question", {"question": question})
                    for question in response.questions
                ],
                update={
                    "questions": response.questions,
                    "feedback_messages": [],
                    "agent_message": "Вопросы сгенерированы автоматически (автономный режим)",
                },
            )

        # Run normal HITL flow
        return await super().__call__(state, config)
