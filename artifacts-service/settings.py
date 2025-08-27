"""Settings configuration for Artifacts Service."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Artifacts Service settings."""

    model_config = SettingsConfigDict(
        env_prefix="ARTIFACTS_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8001, description="Server port")

    # Storage settings
    data_path: Path = Field(
        default=Path("./data/artifacts"), description="Base path for artifacts storage"
    )

    # Limits
    max_file_size: int = Field(
        default=10485760,  # 10MB
        description="Maximum file size in bytes",
    )
    max_files_per_thread: int = Field(
        default=100, description="Maximum number of files per thread"
    )

    # Security
    allowed_content_types: list[str] = Field(
        default=["text/markdown", "application/json", "text/plain"],
        description="Allowed content types",
    )
    max_path_depth: int = Field(default=3, description="Maximum path depth for files")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")


# Global settings instance
settings = Settings()
