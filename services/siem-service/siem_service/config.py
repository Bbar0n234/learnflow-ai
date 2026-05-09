"""SIEM service configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """SIEM service settings."""

    # Database
    database_url: str = "postgresql+asyncpg://siem:siem@localhost/siem"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Security
    jwt_secret: str = "change-me-in-production"

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

    class Config:
        """Pydantic config."""

        env_prefix = "SIEM_"


@lru_cache
def get_settings() -> Settings:
    """Get settings singleton."""
    return Settings()
