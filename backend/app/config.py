from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
    )

    database_url: str = (
        "postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow"
    )
