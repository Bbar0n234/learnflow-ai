from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
    )

    database_url: str = (
        "postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow"
    )

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        import json

        if isinstance(v, str):
            return json.loads(v)
        return v
