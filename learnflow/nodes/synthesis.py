"""
Узел синтезирования материала.
Объединяет сгенерированный материал и распознанные конспекты в финальный документ.
Если конспектов нет - просто использует generated_material.
"""

import logging
from typing import Literal
from langchain_core.messages import SystemMessage
from langgraph.types import Command

from ..state import ExamState
from ..utils import render_system_prompt
from .base import BaseWorkflowNode


logger = logging.getLogger(__name__)


class SynthesisNode(BaseWorkflowNode):
    """
    Узел синтезирования материала на основе сгенерированного контента и распознанных конспектов.
    Простой узел без HITL логики - прямой переход к генерации вопросов.
    """
    
    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()
    
    def get_node_name(self) -> str:
        """Возвращает имя узла для поиска конфигурации"""
        return "synthesis_material"

    async def __call__(self, state: ExamState, config) -> Command[Literal["generating_questions"]]:
        """
        Синтезирует финальный материал из generated_material и recognized_notes.
        
        Args:
            state: Текущее состояние с generated_material и potentially recognized_notes
            config: Конфигурация LangGraph
            
        Returns:
            Command с переходом к генерации вопросов и обновленным состоянием
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting synthesis for thread {thread_id}")
        
        # Проверяем, не установлен ли уже synthesized_material (например, если пропустили recognition)
        if state.synthesized_material:
            logger.info(f"Synthesized material already set for thread {thread_id}, skipping synthesis")
            return Command(
                goto="generating_questions",
                update={}  # Ничего не обновляем, материал уже есть
            )
        
        # Проверяем наличие базового материала
        if not state.generated_material:
            logger.error(f"No generated material found for thread {thread_id}")
            raise ValueError("Отсутствует сгенерированный материал для синтеза")
        
        # Определяем, есть ли распознанные конспекты
        has_recognized_notes = bool(state.recognized_notes and state.recognized_notes.strip())
        
        if has_recognized_notes:
            logger.info(f"Synthesizing with both generated material and recognized notes for thread {thread_id}")
            
            # Формируем промпт для синтеза с конспектами
            prompt_content = render_system_prompt(
                template_type="synthesize",
                exam_question=state.exam_question,
                lecture_notes=state.recognized_notes,
                additional_material=state.generated_material
            )
            
            # Генерируем синтезированный материал
            messages = [SystemMessage(content=prompt_content)]
            response = await self.model.ainvoke(messages)
            synthesized_material = response.content
            
            logger.info(f"Successfully synthesized material with notes for thread {thread_id}")
        else:
            logger.info(f"No recognized notes found, using generated material as synthesis for thread {thread_id}")
            
            # Если нет распознанных конспектов, используем сгенерированный материал как есть
            synthesized_material = state.generated_material
        
        # Обновляем состояние
        update_data = {
            "synthesized_material": synthesized_material
        }
        
        logger.info(f"Synthesis completed for thread {thread_id}. "
                   f"Material length: {len(synthesized_material)} chars, "
                   f"Had notes: {has_recognized_notes}")
        
        return Command(
            goto="generating_questions",
            update=update_data
        ) 