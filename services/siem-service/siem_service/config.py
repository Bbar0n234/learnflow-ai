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

    # Operational knobs — tune without rebuild (D-ERR-9, D-ERR-11)
    # Invariant: redis_socket_timeout > xread_block_ms / 1000 (OQ-D).
    # Default 5s > 1s (xread_block_ms=1000) — blocking XREADGROUP won't hit socket_timeout.
    redis_socket_timeout: float = 5.0
    redis_socket_connect_timeout: float = 5.0
    db_statement_timeout_seconds: int = 120

    @field_validator("frontend_origin", mode="before")
    @classmethod
    def parse_frontend_origin(cls, v: object) -> object:
        # CSV, не JSON: .env шелл-сорсится (Makefile LOAD_ENV), JSON-список
        # с кавычками такой загрузки не переживает.
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
