"""SecurityGuard: Universal prompt injection protection for LearnFlow AI."""

import logging
from typing import Optional

from fuzzysearch import find_near_matches
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from ..utils.utils import render_system_prompt

logger = logging.getLogger(__name__)


class InjectionResult(BaseModel):
    """Результат проверки на injection - structured output"""
    
    has_injection: bool = Field(description="Обнаружена ли попытка инъекции")
    injection_text: Optional[str] = Field(default="", description="Текст инъекции если найден")


class SecurityGuard:
    """Простая универсальная система защиты от prompt injection"""
    
    def __init__(self, model_config: dict, fuzzy_threshold: float = 0.85):
        """Инициализация с конфигурацией через yaml как у других узлов"""
        self.model = ChatOpenAI(
            model=model_config.get('model_name', 'gpt-4.1-mini'),
            temperature=model_config.get('temperature', 0.0),
            max_tokens=model_config.get('max_tokens', 1000),
            api_key=model_config['api_key']
        ).with_structured_output(InjectionResult)
        self.fuzzy_threshold = fuzzy_threshold
    
    async def validate_and_clean(self, text: str) -> str:
        """
        Универсальный метод валидации и очистки текста.
        НИКОГДА не блокирует выполнение - graceful degradation.
        
        Args:
            text: Текст для проверки
            
        Returns:
            Очищенный текст или исходный при ошибке
        """
        if not text or not text.strip():
            return text
            
        try:
            # Проверяем на injection через structured output
            result = await self.model.ainvoke([
                SystemMessage(content=self._get_detection_prompt()),
                HumanMessage(content=text)
            ])
            
            # Если injection найден и указан текст - пытаемся очистить
            if result.has_injection and result.injection_text.strip():
                cleaned = self._fuzzy_remove(text, result.injection_text)
                if cleaned and cleaned != text:
                    logger.info(f"Successfully cleaned injection: {result.injection_text[:50]}...")
                    return cleaned
            
            return text
            
        except Exception as e:
            # При ЛЮБОЙ ошибке возвращаем исходный текст (graceful degradation)
            logger.warning(f"Security check failed, continuing with original text: {e}")
            return text
    
    def _fuzzy_remove(self, document: str, target: str) -> Optional[str]:
        """
        Удаление injection через fuzzy matching - адаптация из edit_material.py
        
        Returns:
            Документ без injection или None если удаление невозможно
        """
        # Edge case: пустые строки
        if not target or not document:
            return None
        
        # Для коротких строк - только точное совпадение
        if len(target) < 10:
            if target in document:
                return document.replace(target, "", 1).strip()
            return None
        
        # Вычисляем дистанцию
        max_distance = max(1, int(len(target) * (1 - self.fuzzy_threshold)))
        
        # Для очень длинных строк ограничиваем дистанцию
        if len(target) > 100:
            max_distance = min(max_distance, 15)
        
        # Поиск
        try:
            matches = find_near_matches(
                target,
                document,
                max_l_dist=max_distance
            )
        except Exception as e:
            logger.error(f"Fuzzy search error: {e}")
            return None
        
        if not matches:
            return None
        
        # Берем первое совпадение и удаляем его
        match = matches[0]
        cleaned_document = (
            document[:match.start] +
            document[match.end:]
        ).strip()
        
        return cleaned_document if cleaned_document else None
    
    def _get_detection_prompt(self) -> str:
        """Промпт для детекции injection из конфига"""
        return render_system_prompt("security_guard_detection")