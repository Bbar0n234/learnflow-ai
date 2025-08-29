"""
Узел для итеративного редактирования синтезированного материала.
Минимальная интеграция MVP на основе рабочего кода из Jupyter notebook.
"""

import logging
from typing import Optional, Tuple
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables.config import RunnableConfig
from langgraph.types import interrupt, Command
from fuzzysearch import find_near_matches

from .base import BaseWorkflowNode
from ..core.state import GeneralState, ActionDecision, EditDetails, EditMessageDetails
# from ..utils.utils import render_system_prompt
from ..services.hitl_manager import get_hitl_manager


class EditMaterialNode(BaseWorkflowNode):
    """
    Узел для редактирования синтезированного материала.
    Использует паттерн HITL для итеративных правок.
    """

    def __init__(self, logger: logging.Logger = None):
        super().__init__(logger)
        self.model = self.create_model()  # Инициализируем при первом вызове

    def get_node_name(self) -> str:
        """Возвращает имя узла для конфигурации"""
        return "edit_material"
    
    def _build_context_from_state(self, state) -> dict:
        """Строит контекст для промпта из состояния workflow"""
        context = {}
        
        if hasattr(state, 'synthesized_material'):
            context['generated_material'] = state.synthesized_material
            
        return context

    def get_model(self):
        """Возвращает модель для обращения к LLM"""
        return self.model

    def fuzzy_find_and_replace(
        self, document: str, target: str, replacement: str, threshold: float = 0.85
    ) -> Tuple[str, bool, Optional[str], float]:
        """
        Нечеткий поиск и замена текста в документе.
        Прямой порт из Jupyter notebook.

        Returns: (new_document, success, found_text, similarity)
        """
        # Edge case: пустые строки
        if not target or not document:
            return document, False, None, 0.0

        # Для коротких строк - только точное совпадение
        if len(target) < 10:
            if target in document:
                idx = document.index(target)
                new_doc = document[:idx] + replacement + document[idx + len(target) :]
                return new_doc, True, target, 1.0
            return document, False, None, 0.0

        # Вычисляем дистанцию
        max_distance = max(1, int(len(target) * (1 - threshold)))

        # Для очень длинных строк ограничиваем дистанцию
        if len(target) > 100:
            max_distance = min(max_distance, 15)

        # Поиск
        try:
            matches = find_near_matches(target, document, max_l_dist=max_distance)
        except Exception as e:
            self.logger.error(f"Fuzzy search error: {e}")
            return document, False, None, 0.0

        if not matches:
            return document, False, None, 0.0

        # Берем первое совпадение
        match = matches[0]

        # Вычисляем similarity
        if len(target) > 0:
            similarity = max(0.0, 1 - (match.dist / len(target)))
        else:
            similarity = 1.0 if match.dist == 0 else 0.0

        # Заменяем
        new_document = document[: match.start] + replacement + document[match.end :]

        return new_document, True, match.matched, similarity

    async def handle_edit_action(
        self, state: GeneralState, action: EditDetails, messages: list
    ) -> Command:
        """Обработка действия редактирования"""
        document = state.synthesized_material

        # Используем fuzzy_find_and_replace
        new_document, success, found_text, similarity = self.fuzzy_find_and_replace(
            document, action.old_text, action.new_text
        )

        if not success:
            # Текст не найден
            error_msg = "Указанный текст не найден в документе. Пожалуйста, проверьте фрагмент и попробуйте снова."
            self.logger.warning(
                f"Text not found: '{action.old_text[:50]}...' (similarity: {similarity:.2f})"
            )

            messages.append(SystemMessage(content=f"[EDIT ERROR]: {error_msg}"))

            return Command(
                goto="edit_material",
                update={
                    "feedback_messages": messages,
                    "needs_user_input": False,
                    "last_action": "edit_error",
                },
            )

        # Успешное редактирование
        edit_count = state.edit_count + 1
        self.logger.info(f"Edit #{edit_count} applied (similarity: {similarity:.2f})")

        messages.append(
            SystemMessage(
                content=f"[EDIT SUCCESS #{edit_count}]: Replaced text (similarity: {similarity:.2f})"
            )
        )

        # Обновляем состояние
        update_dict = {
            "synthesized_material": new_document,
            "feedback_messages": messages,
            "edit_count": edit_count,
            "needs_user_input": not action.continue_editing,
            "last_action": "edit",
        }

        # Если не продолжаем автономно, устанавливаем сообщение
        if not action.continue_editing:
            update_dict["agent_message"] = "Правка внесена. Какие еще изменения нужны?"

        return Command(goto="edit_material", update=update_dict)

    async def handle_message_action(
        self, state: GeneralState, action: EditMessageDetails, messages: list
    ) -> Command:
        """Обработка сообщения пользователю"""
        messages.append(AIMessage(content=action.content))

        return Command(
            goto="edit_material",
            update={
                "feedback_messages": messages,
                "needs_user_input": True,
                "agent_message": action.content,
                "last_action": "message",
            },
        )

    async def handle_complete_action(self, state: GeneralState) -> Command:
        """Завершение редактирования"""
        self.logger.info("Edit session completed")

        return Command(
            goto="generating_questions",  # Переходим к следующему узлу
            update={
                "needs_user_input": True,  # Сбрасываем флаг для следующего узла
                "agent_message": None,
                "last_action": "complete",
                "feedback_messages": [],
            },
        )

    async def __call__(self, state: GeneralState, config: RunnableConfig) -> Command:
        """
        Главная логика узла редактирования.
        Обрабатывает цикл: запрос ввода -> анализ -> действие -> повтор
        """
        thread_id = config.get("configurable", {}).get("thread_id", "unknown")
        self.logger.debug(f"EditMaterialNode called for thread {thread_id}")

        # Проверяем настройки HITL
        hitl_manager = get_hitl_manager()
        hitl_enabled = hitl_manager.is_enabled("edit_material", thread_id)
        self.logger.info(f"HITL for edit_material: {hitl_enabled}")

        # Получаем историю сообщений
        messages = state.feedback_messages.copy() if state.feedback_messages else []

        # Проверяем, есть ли материал для редактирования
        if not state.synthesized_material:
            self.logger.warning("No synthesized material to edit")
            return Command(
                goto="generating_questions",
                update={"agent_message": "Нет материала для редактирования"},
            )

        # Если HITL отключен, пропускаем этот узел
        if not hitl_enabled:
            self.logger.info("HITL disabled for edit_material, skipping to next node")
            return Command(
                goto="generating_questions",
                update={
                    "agent_message": "Материал принят без редактирования (автономный режим)",
                    "last_action": "skip_hitl",
                },
            )

        # Запрашиваем ввод пользователя если нужно
        if state.needs_user_input:
            msg_to_user = state.agent_message or "Какие правки внести в материал? "

            # Используем interrupt для получения ввода
            interrupt_data = {"message": [msg_to_user]}
            user_feedback = interrupt(interrupt_data)

            if user_feedback:
                # Валидация запроса на редактирование в HITL цикле
                if self.security_guard:
                    user_feedback = await self.validate_input(user_feedback)

                messages.append(HumanMessage(content=user_feedback))

                # Сбрасываем флаги и продолжаем обработку
                return Command(
                    goto="edit_material",
                    update={
                        "feedback_messages": messages,
                        "agent_message": None,
                        "needs_user_input": False,
                    },
                )

        # Получаем персонализированный промпт от сервиса с дополнительным контекстом
        extra_context = {
            "template_variant": "initial",
            "generated_material": state.synthesized_material if hasattr(state, 'synthesized_material') else ""
        }
        system_prompt = await self.get_system_prompt(state, config, extra_context)

        # Шаг 1: Определяем тип действия
        model = self.get_model()
        decision = await model.with_structured_output(ActionDecision).ainvoke(
            [SystemMessage(content=system_prompt)] + messages
        )

        self.logger.debug(f"Action decision: {decision.action_type}")
        messages.append(AIMessage(content=decision.model_dump_json()))

        # Шаг 2: Выполняем действие в зависимости от типа
        if decision.action_type == "edit":
            details = await model.with_structured_output(EditDetails).ainvoke(
                [SystemMessage(content=system_prompt)] + messages
            )

            self.logger.info(f"Edit details: {details.model_dump_json()}")

            return await self.handle_edit_action(state, details, messages)

        elif decision.action_type == "message":
            details = await model.with_structured_output(EditMessageDetails).ainvoke(
                [SystemMessage(content=system_prompt)] + messages
            )
            self.logger.info(f"Edit message details: {details.model_dump_json()}")
            return await self.handle_message_action(state, details, messages)

        elif decision.action_type == "complete":
            return await self.handle_complete_action(state)

        # Не должно произойти, но на всякий случай
        self.logger.error(f"Unknown action type: {decision.action_type}")
        return Command(
            goto="edit_material",
            update={
                "needs_user_input": True,
                "agent_message": "Произошла ошибка. Попробуйте еще раз.",
            },
        )
