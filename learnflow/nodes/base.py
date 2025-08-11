"""
Базовые классы для узлов workflow с поддержкой конфигурации LLM моделей.
"""

from abc import ABC, abstractmethod
from langchain_core.runnables.config import RunnableConfig
from langgraph.types import interrupt, Command
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_openai import ChatOpenAI
from typing import Any, Dict
import logging
from ..utils.utils import render_system_prompt
from ..models.model_factory import create_model_for_node
from ..config.config_models import ModelConfig
from ..config.settings import get_settings


class BaseWorkflowNode(ABC):
    """
    Базовый класс для всех узлов workflow с поддержкой конфигурации LLM моделей.
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.settings = get_settings()
    
    @abstractmethod
    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации в graph.yaml"""
        pass
    
    def get_model_config(self) -> ModelConfig:
        """Получает конфигурацию модели для этого узла"""
        from ..config_manager import get_config_manager
        config_manager = get_config_manager()
        return config_manager.get_model_config(self.get_node_name())
    
    def create_model(self) -> ChatOpenAI:
        """Создает модель на основе конфигурации для этого узла"""
        return create_model_for_node(self.get_node_name(), self.settings.openai_api_key)


class FeedbackNode(BaseWorkflowNode):
    """
    Абстрактный базовый класс для узлов, реализующих паттерн
    «генерация — обратная связь — правка — завершение».
    """

    def __init__(self, logger: logging.Logger = None):
        super().__init__(logger)

    @abstractmethod
    def is_initial(self, state) -> bool:
        """Нужно ли делать первую генерацию"""
        pass

    @abstractmethod
    def get_template_type(self) -> str:
        """Возвращает тип шаблона для промпта"""
        pass

    @abstractmethod
    def get_prompt_kwargs(self, state, user_feedback: str = None, config=None) -> Dict[str, Any]:
        """Возвращает параметры для промпта"""
        pass

    def render_prompt(self, state, user_feedback: str = None, config=None) -> str:
        """Формирует промпт для LLM, используя логику initial/further"""
        template_type = self.get_template_type()
        
        # Определяем вариант шаблона
        if user_feedback or not self.is_initial(state):
            template_variant = "further"
        else:
            template_variant = "initial"
        
        # Получаем параметры для промпта
        prompt_kwargs = self.get_prompt_kwargs(state, user_feedback, config)
        
        # Добавляем configurable если есть config
        if config and "configurable" in config:
            prompt_kwargs["configurable"] = config["configurable"]
        
        return render_system_prompt(
            template_type,
            template_variant=template_variant,
            **prompt_kwargs
        )

    @abstractmethod
    def get_model(self):
        """Возвращает LLM/chain"""
        pass

    @abstractmethod
    def format_initial_response(self, response) -> str:
        pass

    @abstractmethod
    def is_approved(self, response) -> bool:
        pass

    @abstractmethod
    def get_next_node(self, state, approved: bool = False) -> str:
        pass

    @abstractmethod
    def get_user_prompt(self) -> str:
        pass

    @abstractmethod
    def get_update_on_approve(self, state, response) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_current_node_name(self) -> str:
        pass

    # ------- helpers -------
    def get_initial_update(self, response) -> Dict[str, Any]:
        formatted = self.format_initial_response(response)
        return {"feedback_messages": [AIMessage(content=formatted)]}

    def get_continue_update(self, state, user_feedback: str, response) -> Dict[str, Any]:
        self.logger.debug(f"User feedback: {user_feedback}")
        self.logger.debug(f"Response: {response}")
        formatted = self.format_initial_response(response)
        self.logger.debug(f"Formatted: {formatted}")
        return {
            "feedback_messages": state.feedback_messages + [
                HumanMessage(content=user_feedback),
                AIMessage(content=formatted),
            ]
        }

    async def __call__(self, state, config: RunnableConfig) -> Command:
        thread_id = config["configurable"]["thread_id"]
        self.logger.debug(f"Processing {self.__class__.__name__} for thread {thread_id}")

        # 1. Первая генерация
        if self.is_initial(state):
            prompt = self.render_prompt(state, config=config)
            model = self.get_model()
            response = await model.ainvoke([SystemMessage(content=prompt)])
            return Command(
                goto=self.get_current_node_name(),
                update=self.get_initial_update(response),
            )

        # 2. Запрос обратной связи
        messages_for_user = [state.feedback_messages[-1].content]
        if len(state.feedback_messages) == 1:
            messages_for_user.append(self.get_user_prompt())
        interrupt_json = {"message": messages_for_user}
        user_feedback = interrupt(interrupt_json)

        # 3. Правка с учётом feedback
        prompt = self.render_prompt(state, user_feedback=user_feedback, config=config)
        model = self.get_model()
        messages = [SystemMessage(content=prompt)] + state.feedback_messages + [
            HumanMessage(content=user_feedback)
        ]
        response = await model.ainvoke(messages)
        self.logger.debug(f"Response: {response}")

        # 4. Проверка approve
        if self.is_approved(response):
            self.logger.debug(f"Approved: {response}")
            return Command(
                goto=self.get_next_node(state, approved=True),
                update=self.get_update_on_approve(state, response),
            )
        
        self.logger.debug(f"Not approved: {response}")
        goto = self.get_current_node_name()
        self.logger.debug(f"Goto: {goto}")
        update = self.get_continue_update(state, user_feedback, response)
        self.logger.debug(f"Update: {update}")
        return Command(
            goto=goto,
            update=update,
        ) 