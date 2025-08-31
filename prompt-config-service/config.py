"""Configuration settings for the prompt configuration service."""

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""
    
    # Database
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5433/prompts_db",
        alias="PROMPT_CONFIG_DATABASE_URL",
        description="PostgreSQL database URL"
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Database pool max overflow")
    
    # Service
    service_name: str = Field(default="prompt-config-service", description="Service name")
    service_version: str = Field(default="1.0.0", description="Service version")
    service_port: int = Field(default=8002, description="Service port")
    service_host: str = Field(default="0.0.0.0", description="Service host")
    
    # Paths
    prompts_config_path: str = Field(
        default="../configs/prompts.yaml", 
        description="Path to prompts configuration file"
    )
    initial_data_path: str = Field(
        default="./seed/initial_data.json",
        description="Path to initial seed data"
    )
    
    # Cache
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    model_config = {
        "env_file": [".env.local", ".env"],
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore"
    }


# Global settings instance
settings = Settings()