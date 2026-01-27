"""
Узел обработки учебных конспектов.
Простая логика без HITL: обрабатывает изображения если есть, запрашивает один раз если нет.
"""

import base64
import logging
from typing import List
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from ..core.state import GeneralState
from .base import BaseWorkflowNode


logger = logging.getLogger(__name__)


def load_images_as_base64(image_paths: List[str]) -> List[str]:
    """
    Загружает изображения в base64 формат.

    Args:
        image_paths: Список путей к изображениям

    Returns:
        Список base64 строк изображений
    """
    base64_images = []
    for image_path in image_paths:
        try:
            with open(image_path, "rb") as image_file:
                base64_string = base64.b64encode(image_file.read()).decode("utf-8")
                base64_images.append(base64_string)
                logger.info(f"Loaded image: {image_path}")
        except Exception as e:
            logger.error(f"Failed to load image {image_path}: {e}")

    return base64_images


class RecognitionNode(BaseWorkflowNode):
    """
    Узел обработки учебных конспектов с поддержкой:
    - Обработки конспектов в любом формате (изображения или текст)
    - Прямого ввода текстовых конспектов
    - Валидации минимальной длины текста
    - Пропуска обработки по желанию пользователя
    """
    
    MIN_TEXT_LENGTH = 50  # Минимальная длина для валидного текста конспекта

    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()

    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "recognition_handwritten"
    
    def _build_context_from_state(self, state) -> dict:
        """Строит контекст для промпта из состояния workflow"""
        return {
            # Узел recognition не требует контекста из state для промпта
        }

    async def __call__(self, state: GeneralState, config) -> Command:
        """
        Основная логика узла распознавания.

        Args:
            state: Текущее состояние с потенциальными image_paths
            config: Конфигурация LangGraph

        Returns:
            Command с переходом к следующему узлу
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting recognition processing for thread {thread_id}")

        # Случай 1: Есть изображения - обрабатываем их
        if state.image_paths:
            logger.info(
                f"Found {len(state.image_paths)} images, processing recognition"
            )

            try:
                # Обрабатываем изображения
                recognized_text = await self._process_images(state.image_paths, state, config)

                if recognized_text:
                    logger.info(
                        f"Successfully recognized text from images for thread {thread_id}"
                    )
                    # M2-01: Recognition moved before planning
                    return Command(
                        goto="planning_structure",
                        update={"recognized_notes": recognized_text},
                    )
                else:
                    logger.warning(
                        f"Failed to recognize text from images for thread {thread_id}"
                    )
                    # При ошибке распознавания пропускаем синтез
                    return Command(
                        goto="generating_questions",
                        update={
                            "recognized_notes": "",
                            "synthesized_material": state.generated_material
                        }
                    )

            except Exception as e:
                logger.error(f"Error processing images for thread {thread_id}: {e}")
                # В случае ошибки пропускаем синтез
                return Command(
                    goto="generating_questions",
                    update={
                        "recognized_notes": "",
                        "synthesized_material": state.generated_material
                    }
                )

        # Случай 2: Нет изображений - запрашиваем конспекты у пользователя
        logger.info(f"No images found for thread {thread_id}, requesting notes from user")

        # Запрашиваем конспекты у пользователя (изображения или текст)
        message_content = (
            "📸 Для улучшения качества материала можете добавить конспекты с занятий.\n\n"
            "Варианты действий:\n"
            "• Отправьте фото конспектов или вставьте текст\n"
            "• Материалы принимаются в любом формате\n"
            "• Напишите 'пропустить' для продолжения без конспектов"
        )

        # Делаем interrupt для получения ответа пользователя
        interrupt_json = {"message": [message_content]}
        user_response = interrupt(interrupt_json)

        # Обрабатываем ответ пользователя
        # Проверяем длину текста - менее 50 символов означает пропуск
        cleaned_text = user_response.strip()
        if len(cleaned_text) < self.MIN_TEXT_LENGTH:
            logger.info(f"Text too short ({len(cleaned_text)} chars), user wants to skip notes for thread {thread_id}")
            # Текст слишком короткий - пользователь хочет пропустить
            return Command(
                goto="generating_questions",
                update={
                    "recognized_notes": "",
                    "synthesized_material": state.generated_material,  # Используем generated_material как финальный
                },
            )
        
        # Текст достаточной длины - используем как распознанные конспекты
        logger.info(f"Received text notes ({len(cleaned_text)} chars) for thread {thread_id}, proceeding to planning_structure")
        # M2-01: Recognition moved before planning
        return Command(
            goto="planning_structure",
            update={"recognized_notes": cleaned_text}
        )

    async def _process_images(self, image_paths: List[str], state: GeneralState, config) -> str:
        """
        Обрабатывает изображения с помощью GPT-4-vision.

        Args:
            image_paths: Список путей к изображениям
            state: Состояние workflow
            config: Конфигурация LangGraph

        Returns:
            Распознанный текст или пустая строка при ошибке
        """
        import time
        start_time = time.time()
        try:
            # Загружаем изображения в base64
            base64_images = load_images_as_base64(image_paths)
            if not base64_images:
                logger.error("Failed to load any images for recognition")
                return ""

            # Получаем персонализированный промпт от сервиса
            system_content = await self.get_system_prompt(state, config)

            # Создаем контент с изображениями для GPT-4-vision
            user_content = [
                {
                    "type": "text",
                    "text": "Вот изображения рукописных конспектов для распознавания:",
                }
            ]

            for base64_img in base64_images:
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_img}"},
                    }
                )

            # Создаем сообщения для модели
            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content),
            ]

            # Отправляем запрос к модели
            response = await self.model.ainvoke(messages)

            # Обрабатываем ответ (убираем секцию рассуждений)
            content = response.content
            if "[END OF REASONING]" in content:
                content = content.split("[END OF REASONING]")[1].strip()

            # Валидация распознанного текста из рукописных конспектов
            if self.security_guard and content:
                content = await self.validate_input(content)

            elapsed = time.time() - start_time
            if elapsed > 5.0:
                logger.warning(f"Image recognition completed in {elapsed:.2f}s (slow), text length: {len(content)} chars")
            else:
                logger.info(f"Image recognition completed in {elapsed:.2f}s, text length: {len(content)} chars")
            
            return content

        except Exception as e:
            logger.error(f"Error in image processing: {e}")
            return ""
