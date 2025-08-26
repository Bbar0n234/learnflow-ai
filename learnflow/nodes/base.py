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
from ..models.model_factory import create_model_for_node
from ..config.config_models import ModelConfig
from ..config.settings import get_settings
from ..services.prompt_client import PromptConfigClient, WorkflowExecutionError


class BaseWorkflowNode(ABC):
    """
    Базовый класс для всех узлов workflow с поддержкой конфигурации LLM моделей.
    """

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.settings = get_settings()
        self._init_security()
        self._init_prompt_client()
    
    def _init_prompt_client(self):
        """Инициализация клиента для Prompt Configuration Service"""
        try:
            self.prompt_client = PromptConfigClient()
            self.logger.debug(f"Prompt client initialized for {self.__class__.__name__}")
        except Exception as e:
            self.logger.warning(f"Failed to initialize prompt client: {e}")
            self.prompt_client = None

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
        return create_model_for_node(self.get_node_name())

    def _init_security(self):
        """Инициализация SecurityGuard с конфигурацией через yaml"""
        self.security_guard = None
        self.logger.debug(
            f"Initializing security guard. Enabled: {self.settings.security_enabled}"
        )

        if self.settings.security_enabled:
            try:
                from ..security.guard import SecurityGuard, InjectionResult
                from ..config.config_manager import get_config_manager
                from ..models.model_factory import get_model_factory

                # Получаем конфигурацию security guard
                config_manager = get_config_manager()
                security_config = config_manager.get_model_config("security_guard")
                self.logger.debug(f"Got security config: {security_config}")
                
                # Создаем модель через фабрику для корректной поддержки провайдеров
                factory = get_model_factory()
                security_model = factory.create_model(security_config)
                
                # SecurityGuard теперь получает готовую модель
                self.security_guard = SecurityGuard(
                    model=security_model.with_structured_output(InjectionResult),
                    fuzzy_threshold=self.settings.security_fuzzy_threshold,
                )
                self.logger.info(
                    f"Security guard initialized successfully for {self.__class__.__name__}"
                )
            except Exception as e:
                self.logger.warning(f"Failed to initialize security guard: {e}")
                self.security_guard = None

    async def validate_input(self, content: str) -> str:
        """
        Универсальная валидация любого пользовательского контента.
        Всегда возвращает валидный результат (graceful degradation).

        Args:
            content: Контент для валидации

        Returns:
            Безопасный контент (очищенный или исходный при ошибке)
        """
        if (
            not self.security_guard
            or not content
            or len(content) < self.settings.security_min_content_length
        ):
            return content

        cleaned = await self.security_guard.validate_and_clean(content)

        if cleaned != content:
            self.logger.info(f"Content sanitized in {self.get_node_name()}")

        return cleaned

    async def get_system_prompt(self, state, config: RunnableConfig, extra_context: Dict[str, Any] = None) -> str:
        """
        Получает системный промпт из Prompt Configuration Service.
        
        Args:
            state: Состояние workflow
            config: Конфигурация LangGraph
            extra_context: Дополнительный контекст для промпта (не из state)
            
        Returns:
            Системный промпт
            
        Raises:
            WorkflowExecutionError: При недоступности сервиса
        """
        if not self.prompt_client:
            raise WorkflowExecutionError("Prompt service is not configured")
        
        try:
            # Извлекаем user_id из thread_id (по соглашению они равны)
            thread_id = config["configurable"]["thread_id"]
            try:
                user_id = int(thread_id)
            except (ValueError, TypeError):
                self.logger.error(f"Invalid thread_id format: {thread_id}. Expected numeric string.")
                raise WorkflowExecutionError(f"Invalid thread_id format: {thread_id}")
            
            # Формируем контекст из состояния workflow
            context = self._build_context_from_state(state)
            
            # Добавляем дополнительный контекст если есть
            if extra_context:
                context.update(extra_context)
            
            # Получаем промпт от сервиса
            prompt = await self.prompt_client.generate_prompt(
                user_id=user_id,
                node_name=self.get_node_name(),
                context=context
            )
            
            self.logger.info(f"Received personalized prompt from service for user {user_id}")
            return prompt
            
        except WorkflowExecutionError:
            # Перебрасываем ошибки сервиса без изменений
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error getting prompt: {e}")
            raise WorkflowExecutionError(f"Failed to get prompt: {e}")
    
    
    def _build_context_from_state(self, state) -> Dict[str, Any]:
        """
        Строит контекст для промпта из состояния workflow.
        Подклассы должны переопределить для специфичного маппинга.
        
        Args:
            state: Состояние workflow
            
        Returns:
            Словарь с контекстными данными
        """
        # Базовая реализация возвращает пустой контекст
        # Каждый узел должен переопределить для своего маппинга
        return {}


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
    def get_prompt_kwargs(
        self, state, user_feedback: str = None, config=None
    ) -> Dict[str, Any]:
        """Возвращает параметры для промпта"""
        pass

    async def render_prompt(self, state, user_feedback: str = None, config=None) -> str:
        """Формирует промпт для LLM, используя логику initial/further"""
        # Определяем вариант шаблона
        if user_feedback or not self.is_initial(state):
            template_variant = "further"
        else:
            template_variant = "initial"

        # Получаем параметры для промпта
        prompt_kwargs = self.get_prompt_kwargs(state, user_feedback, config)
        
        # Добавляем template_variant и configurable в extra_context
        extra_context = {
            "template_variant": template_variant,
            **prompt_kwargs
        }
        
        if config and "configurable" in config:
            extra_context["configurable"] = config["configurable"]
        
        # Вызываем get_system_prompt с extra_context
        return await self.get_system_prompt(state, config, extra_context)

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

    def get_continue_update(
        self, state, user_feedback: str, response
    ) -> Dict[str, Any]:
        self.logger.debug(f"User feedback: {user_feedback}")
        self.logger.debug(f"Response: {response}")
        formatted = self.format_initial_response(response)
        self.logger.debug(f"Formatted: {formatted}")
        return {
            "feedback_messages": state.feedback_messages
            + [
                HumanMessage(content=user_feedback),
                AIMessage(content=formatted),
            ]
        }

    async def __call__(self, state, config: RunnableConfig) -> Command:
        thread_id = config["configurable"]["thread_id"]
        self.logger.debug(
            f"Processing {self.__class__.__name__} for thread {thread_id}"
        )

        # 1. Первая генерация
        if self.is_initial(state):
            prompt = await self.render_prompt(state, config=config)
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

        # Валидация пользовательского feedback с graceful degradation
        if user_feedback and self.security_guard:
            user_feedback = await self.validate_input(user_feedback)

        # 3. Правка с учётом feedback
        prompt = await self.render_prompt(state, user_feedback=user_feedback, config=config)
        model = self.get_model()
        messages = (
            [SystemMessage(content=prompt)]
            + state.feedback_messages
            + [HumanMessage(content=user_feedback)]
        )
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
