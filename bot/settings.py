"""
Настройки Telegram бота.
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class TelegramSettings(BaseSettings):
    """Настройки Telegram бота"""

    token: str = Field(..., description="Telegram bot token")
    webhook_url: Optional[str] = Field(default=None, description="Webhook URL для бота")
    webhook_path: str = Field(default="/webhook", description="Путь для webhook")

    class Config:
        env_prefix = "TELEGRAM_"
        extra = "ignore"


class APISettings(BaseSettings):
    """Настройки для подключения к LearnFlow API"""

    learnflow_host: str = Field(default="localhost", description="Host LearnFlow API")
    learnflow_port: int = Field(default=8000, description="Port LearnFlow API")

    class Config:
        env_prefix = "LEARNFLOW_"
        extra = "ignore"


class PromptServiceSettings(BaseSettings):
    """Настройки для подключения к Prompt Configuration Service"""

    url: str = Field(default="http://localhost:8002", description="Full URL for Prompt Config Service")
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")

    class Config:
        env_prefix = "PROMPT_SERVICE_"
        extra = "ignore"


class BotSettings(BaseSettings):
    """Основные настройки бота"""

    telegram: TelegramSettings = Field(
        default_factory=lambda: TelegramSettings(token="")
    )
    api: APISettings = Field(default_factory=APISettings)
    prompt_service: PromptServiceSettings = Field(default_factory=PromptServiceSettings)

    class Config:
        env_file = ".env"
        env_nested_delimiter = "_"
        extra = "ignore"


# Глобальный экземпляр настроек
_settings: Optional[BotSettings] = None


def get_settings() -> BotSettings:
    """Singleton для получения настроек"""
    global _settings
    if _settings is None:
        _settings = BotSettings()
    return _settings
