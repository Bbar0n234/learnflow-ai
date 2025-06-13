"""
Настройки LearnFlow сервиса.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Основные настройки LearnFlow сервиса"""
    
    # OpenAI settings
    openai_api_key: str = Field(..., env="OPENAI_API_KEY", description="OpenAI API ключ")
    model_name: str = Field(default="gpt-4.1-mini", description="Модель для LLM")
    temperature: float = Field(default=0.1, description="Temperature для генерации")
    
    # PostgreSQL settings для AsyncPostgresSaver
    database_url: str = Field(
        description="PostgreSQL connection string для checkpointer"
    )
    
    # LangFuse settings
    langfuse_public_key: str = Field(..., env="LANGFUSE_PUBLIC_KEY", description="LangFuse public key")
    langfuse_secret_key: str = Field(..., env="LANGFUSE_SECRET_KEY", description="LangFuse secret key")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", env="LANGFUSE_HOST", description="LangFuse host")
    
    # Пути к конфигурационным файлам
    prompts_config_path: str = Field(default="./config/prompts.yaml", env="PROMPTS_CONFIG_PATH", description="Путь к промптам")
    graph_config_path: str = Field(default="./config/graph.yaml", env="GRAPH_CONFIG_PATH", description="Путь к конфигурации графа")
    main_dir: str = Field(default="./data", env="MAIN_DIR", description="Рабочая директория")
    
    # Настройки сервиса
    host: str = Field(default="0.0.0.0", env="LEARNFLOW_HOST", description="Host для FastAPI сервиса")
    port: int = Field(default=8000, env="LEARNFLOW_PORT", description="Port для FastAPI сервиса")
    
    # GitHub integration (optional)
    github_token: Optional[str] = Field(default=None, description="GitHub token для пуша артефактов")
    github_repository: Optional[str] = Field(default=None, description="GitHub репозиторий")
    github_branch: str = Field(default="main", description="GitHub ветка")
    github_base_path: str = Field(default="artifacts", description="Базовый путь в репозитории")
    github_artifacts_base_url: str = Field(
        default="https://github.com",
        description="Базовый URL для артефактов"
    )

    log_level: str = Field(default="DEBUG", env="LOG_LEVEL", description="Уровень логирования")
    
    def is_github_configured(self) -> bool:
        """Проверка настройки GitHub интеграции"""
        return bool(self.github_token and self.github_repository)

    class Config:
        env_file = ".env"
        extra = "ignore"  # Игнорировать лишние переменные окружения


# Глобальный экземпляр настроек
_settings: Optional[AppSettings] = None


def get_settings() -> AppSettings:
    """Singleton для получения настроек"""
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings 