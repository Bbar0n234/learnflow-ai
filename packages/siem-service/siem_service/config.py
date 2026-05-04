"""SIEM service configuration."""

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

    class Config:
        """Pydantic config."""

        env_prefix = "SIEM_"
