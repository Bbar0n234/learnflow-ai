"""SIEM service configuration."""

from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """SIEM service settings."""

    model_config = SettingsConfigDict(env_prefix="SIEM_")

    # Database
    database_url: str = "postgresql+asyncpg://siem:siem@localhost/siem"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Security — обязательный, сервис не стартует без SIEM_JWT_SECRET
    jwt_secret: str

    # CORS — origins фронтенда (CSV в env: SIEM_FRONTEND_ORIGIN).
    # NoDecode: иначе pydantic-settings декодирует list[str] из env как JSON
    # ещё до field validator'а
    frontend_origin: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Event processing
    xread_batch_size: int = 100
    xread_block_ms: int = 1000
    poll_interval_seconds: int = 10

    # Retention
    delete_after_days: int = 90

    # Correlation
    # Max age of an existing "new" alert before correlation creates a fresh one
    # instead of appending. Operational knob — change without rebuild.
    alert_open_window_seconds: int = 86400

    # Event pipeline: max PEL delivery attempts before terminal drop (D-ERR-7, OQ-E).
    # After this many re-deliveries the message is dropped + XACK with logger.error.
    max_delivery_attempts: int = 5

    @field_validator("frontend_origin", mode="before")
    @classmethod
    def parse_frontend_origin(cls, v: object) -> object:
        # CSV, не JSON: .env шелл-сорсится (Makefile LOAD_ENV), JSON-список
        # с кавычками такой загрузки не переживает.
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
