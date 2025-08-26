"""
HTTP клиент для взаимодействия с Prompt Configuration Service.
"""

import asyncio
import httpx
from typing import Optional, Dict, Any
import logging
from ..config.settings import get_settings

logger = logging.getLogger(__name__)


class WorkflowExecutionError(Exception):
    """Исключение для критических ошибок workflow, требующих остановки."""
    pass


class PromptConfigClient:
    """
    MVP версия клиента для Prompt Configuration Service с retry механизмом.
    При недоступности сервиса выбрасывает WorkflowExecutionError без fallback.
    """
    
    def __init__(self, base_url: str = None, timeout: int = None, retry_count: int = None):
        self.settings = get_settings()
        self.base_url = base_url or self.settings.prompt_service_url
        self.timeout = timeout or self.settings.prompt_service_timeout
        self.retry_count = retry_count or self.settings.prompt_service_retry_count
        self.retry_delay = 0.5  # секунды
        self.logger = logger
    
    async def generate_prompt(self, user_id: int, node_name: str, context: Dict[str, Any]) -> str:
        """
        Получает промпт из сервиса конфигурации с retry механизмом.
        При недоступности сервиса - выбрасывает ошибку (без fallback).
        
        Args:
            user_id: ID пользователя (извлекается из thread_id)
            node_name: Имя узла LangGraph (например, 'generating_content')
            context: Контекст workflow для подстановки в шаблон
            
        Returns:
            str: Сгенерированный промпт
            
        Raises:
            WorkflowExecutionError: При недоступности сервиса после всех retry попыток
        """
        last_error: Optional[Exception] = None
        
        self.logger.info(f"Requesting prompt for user_id={user_id}, node={node_name}")
        
        for attempt in range(self.retry_count):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/v1/generate-prompt",
                        json={
                            "user_id": user_id,
                            "node_name": node_name,
                            "context": context
                        }
                    )
                    response.raise_for_status()
                    
                    result = response.json()
                    prompt = result.get("prompt")
                    
                    if not prompt:
                        raise ValueError("Empty prompt received from service")
                    
                    # Валидация минимальной длины промпта
                    if len(prompt) < 50:
                        raise ValueError(f"Prompt too short ({len(prompt)} chars): {prompt[:100]}")
                    
                    self.logger.info(f"Successfully received prompt ({len(prompt)} chars) for {node_name}")
                    return prompt
                    
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError, ValueError) as e:
                last_error = e
                self.logger.warning(f"Attempt {attempt + 1}/{self.retry_count} failed for {node_name}: {e}")
                
                if attempt < self.retry_count - 1:
                    # Экспоненциальная задержка между попытками
                    delay = self.retry_delay * (2 ** attempt)
                    self.logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
        
        # Все попытки исчерпаны - выбрасываем ошибку
        error_msg = (
            f"Prompt configuration service is unavailable after {self.retry_count} attempts. "
            f"Please try again in a few minutes. Last error: {last_error}"
        )
        self.logger.error(error_msg)
        raise WorkflowExecutionError(error_msg)