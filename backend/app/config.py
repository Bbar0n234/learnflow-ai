from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
    )

    database_url: str = (
        "postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow"
    )

    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"

    log_level: str = "info"
    log_file: str = ""

    # Auth
    jwt_secret: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    secure_cookies: bool = True

    # Langfuse Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Langfuse prompt management
    langfuse_prompt_label: str = "development"
    langfuse_prompt_cache_ttl: int = 60

    # MCP encryption
    mcp_encryption_key: str = ""

    # Redis (trace storage for feedback persistence)
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @property
    def langgraph_database_url(self) -> str:
        """PostgreSQL URL for LangGraph (without +psycopg dialect)."""
        return self.database_url.replace("+psycopg", "")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        import json

        if isinstance(v, str):
            return json.loads(v)
        return v
