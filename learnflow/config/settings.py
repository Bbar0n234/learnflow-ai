"""
Настройки LearnFlow сервиса.
"""

from typing import Optional, List
from pydantic import Field
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Основные настройки LearnFlow сервиса"""

    # OpenAI settings
    openai_api_key: str = Field(description="OpenAI API ключ")

    # PostgreSQL settings для AsyncPostgresSaver
    database_url: str = Field(
        description="PostgreSQL connection string для checkpointer"
    )

    # LangFuse settings
    langfuse_public_key: Optional[str] = Field(
        default=None, description="LangFuse public key"
    )
    langfuse_secret_key: Optional[str] = Field(
        default=None, description="LangFuse secret key"
    )
    langfuse_host: str = Field(
        default="https://localhost:3000",
        description="LangFuse host",
    )

    # Пути к конфигурационным файлам
    prompts_config_path: str = Field(
        default="./configs/prompts.yaml",
        description="Путь к промптам",
    )
    graph_config_path: str = Field(
        default="./configs/graph.yaml",
        description="Путь к конфигурации графа",
    )
    main_dir: str = Field(default="./data", description="Рабочая директория")

    # Настройки для работы с изображениями
    max_image_size: int = Field(
        default=10 * 1024 * 1024,
        description="Максимальный размер изображения в байтах (10MB)",
    )
    max_images_per_request: int = Field(
        default=10, description="Максимальное количество изображений за запрос"
    )
    temp_storage_path: str = Field(
        default="/tmp/learnflow", description="Временное хранилище для изображений"
    )
    supported_image_formats: List[str] = Field(
        default=[".jpg", ".jpeg", ".png"],
        description="Поддерживаемые форматы изображений",
    )

    # Настройки сервиса
    host: str = Field(default="0.0.0.0", description="Host для FastAPI сервиса")
    port: int = Field(default=8000, description="Port для FastAPI сервиса")

    # Local artifacts storage
    artifacts_base_path: str = Field(
        default="data/artifacts", description="Базовый путь для локальных артефактов"
    )
    artifacts_ensure_permissions: bool = Field(
        default=True, description="Обеспечение прав доступа для файлов"
    )
    artifacts_max_file_size: int = Field(
        default=10 * 1024 * 1024,
        description="Максимальный размер файла артефакта (10MB)",
    )
    artifacts_atomic_writes: bool = Field(
        default=True, description="Использовать атомарную запись файлов"
    )

    log_level: str = Field(default="DEBUG", description="Уровень логирования")

    # Security settings
    security_enabled: bool = Field(
        default=True,
        description="Включить систему защиты от prompt injection",
    )
    security_fuzzy_threshold: float = Field(
        default=0.85,
        description="Порог fuzzy matching для очистки",
    )
    security_min_content_length: int = Field(
        default=10,
        description="Минимальная длина контента для валидации",
    )

    # Prompt Configuration Service settings
    prompt_service_url: str = Field(
        default="http://localhost:8002",
        description="URL Prompt Configuration Service",
    )
    prompt_service_timeout: int = Field(
        default=5,
        description="Timeout для запросов к Prompt Service (секунды)",
    )
    prompt_service_retry_count: int = Field(
        default=3,
        description="Количество retry попыток для Prompt Service",
    )

    def is_artifacts_configured(self) -> bool:
        """Проверка настройки локального хранилища артефактов"""
        return bool(self.artifacts_base_path)

    def is_langfuse_configured(self) -> bool:
        """Проверка настройки LangFuse интеграции"""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

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
