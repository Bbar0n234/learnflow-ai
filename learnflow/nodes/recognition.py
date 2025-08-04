"""
Узел распознавания рукописных конспектов.
Простая логика без HITL: обрабатывает изображения если есть, запрашивает один раз если нет.
"""

import base64
import logging
from typing import List
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.types import Command, interrupt

from ..state import ExamState
from ..utils import render_system_prompt
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
                base64_string = base64.b64encode(image_file.read()).decode('utf-8')
                base64_images.append(base64_string)
                logger.info(f"Loaded image: {image_path}")
        except Exception as e:
            logger.error(f"Failed to load image {image_path}: {e}")
    
    return base64_images


class RecognitionNode(BaseWorkflowNode):
    """
    Узел распознавания рукописных конспектов.
    Простая логика:
    1. Если есть изображения - обрабатываем их
    2. Если изображений нет - запрашиваем их у пользователя один раз
    3. Если пользователь не предоставил - переходим к концу workflow
    """
    
    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()
    
    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "recognition_handwritten"

    async def __call__(self, state: ExamState, config) -> Command:
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
            logger.info(f"Found {len(state.image_paths)} images, processing recognition")
            
            try:
                # Обрабатываем изображения
                recognized_text = await self._process_images(state.image_paths)
                
                if recognized_text:
                    logger.info(f"Successfully recognized text from images for thread {thread_id}")
                    return Command(
                        goto="synthesis_material",
                        update={"recognized_notes": recognized_text}
                    )
                else:
                    logger.warning(f"Failed to recognize text from images for thread {thread_id}")
                    # Продолжаем без распознанного текста
                    return Command(
                        goto="synthesis_material",
                        update={"recognized_notes": ""}
                    )
                    
            except Exception as e:
                logger.error(f"Error processing images for thread {thread_id}: {e}")
                # В случае ошибки продолжаем без распознавания
                return Command(
                    goto="synthesis_material",
                    update={"recognized_notes": ""}
                )
        
        # Случай 2: Нет изображений - запрашиваем их у пользователя один раз
        logger.info(f"No images found for thread {thread_id}, requesting from user")
        
        # Запрашиваем изображения у пользователя
        message_content = (
            "У вас нет загруженных изображений конспектов. "
            "Для улучшения качества материала рекомендуется загрузить фотографии ваших конспектов.\n\n"
            "Варианты действий:\n"
            "1. Отправьте фотографии ваших конспектов через Telegram бот\n"
            "2. Напишите 'пропустить' для продолжения без изображений"
        )
        
        # Делаем interrupt для получения ответа пользователя
        interrupt_json = {"message": [message_content]}
        user_response = interrupt(interrupt_json)
        
        # Обрабатываем ответ пользователя
        skip_keywords = ["пропустить", "skip", "пропуск", "без изображений", "продолжить", "нет"]
        if any(keyword in user_response.lower() for keyword in skip_keywords):
            logger.info(f"User chose to skip image recognition for thread {thread_id}")
            
            # Пользователь пропустил - переходим сразу к концу workflow (generating_questions)
            # Пропускаем synthesis, так как нет дополнительного материала для синтеза
            return Command(
                goto="generating_questions",
                update={
                    "recognized_notes": "",
                    "synthesized_material": state.generated_material  # Используем generated_material как финальный
                }
            )
        
        # Пользователь хочет добавить изображения, но через API это нужно делать отдельно
        # В рамках текущего workflow мы не можем добавить новые изображения
        # Информируем пользователя и продолжаем без изображений
        logger.info(f"User requested to add images but workflow cannot handle new uploads for thread {thread_id}")
        
        return Command(
            goto="generating_questions", 
            update={
                "recognized_notes": "",
                "synthesized_material": state.generated_material,
                "feedback_messages": [
                    AIMessage(content=(
                        "Для добавления изображений необходимо начать новую сессию и загрузить фотографии сразу с вопросом. "
                        "Продолжаем обработку без изображений конспектов."
                    ))
                ]
            }
        )

    async def _process_images(self, image_paths: List[str]) -> str:
        """
        Обрабатывает изображения с помощью GPT-4-vision.
        
        Args:
            image_paths: Список путей к изображениям
            
        Returns:
            Распознанный текст или пустая строка при ошибке
        """
        try:
            # Загружаем изображения в base64
            base64_images = load_images_as_base64(image_paths)
            if not base64_images:
                logger.error("Failed to load any images for recognition")
                return ""
            
            # Формируем системный промпт
            system_content = render_system_prompt("recognition")
            
            # Создаем контент с изображениями для GPT-4-vision
            user_content = [
                {"type": "text", "text": "Вот изображения рукописных конспектов для распознавания:"}
            ]
            
            for base64_img in base64_images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_img}"}
                })
            
            # Создаем сообщения для модели
            messages = [
                SystemMessage(content=system_content),
                HumanMessage(content=user_content)
            ]
            
            # Отправляем запрос к модели
            response = await self.model.ainvoke(messages)
            
            # Обрабатываем ответ (убираем секцию рассуждений)
            content = response.content
            if "[END OF REASONING]" in content:
                content = content.split("[END OF REASONING]")[1].strip()
            
            return content
            
        except Exception as e:
            logger.error(f"Error in image processing: {e}")
            return "" 