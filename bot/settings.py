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
    
    learnflow_host: str = Field(default="localhost", env="LEARNFLOW_HOST", description="Host LearnFlow API")
    learnflow_port: int = Field(default=8000, env="LEARNFLOW_PORT", description="Port LearnFlow API")

    class Config:
        env_prefix = ""
        extra = "ignore"


class BotSettings(BaseSettings):
    """Основные настройки бота"""
    
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    api: APISettings = Field(default_factory=APISettings)

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