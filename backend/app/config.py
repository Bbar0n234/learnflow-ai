from typing import Annotated, Literal
from urllib.parse import quote, urlencode

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
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

    # Client IP
    client_ip_source: Literal["socket", "x-real-ip", "x-forwarded-for"] = "socket"
    client_ip_xff_hops: int = Field(1, ge=1)

    # OAuth providers — пустой креды-дефолт выключает провайдера (не fail-fast-секрет)
    oauth_yandex_client_id: str = ""
    oauth_yandex_client_secret: str = ""
    oauth_google_client_id: str = ""
    oauth_google_client_secret: str = ""
    oauth_github_client_id: str = ""
    oauth_github_client_secret: str = ""
    # Local dev через Vite; docker-compose разводит свой дефолт (:8000, SPA отдаёт backend)
    oauth_redirect_base_url: str = "http://localhost:5173"
    oauth_http_timeout_seconds: int = 10

    # GeoIP (гео-gate) — путь к MMDB (IPinfo Lite); пусто/недоступна → fallback-страна.
    # Разрешённые для RU провайдеры ({"yandex"}) — бизнес-инвариант в коде, не env.
    geoip_db_path: str = ""
    geoip_fallback_country: str = "RU"

    # Langfuse Observability
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"

    # Langfuse prompt management
    langfuse_prompt_label: str = "development"
    langfuse_prompt_cache_ttl: int = 60

    # Security (prompt injection protection)
    canary_secret: str = ""
    # Операционный тумблер: выключает inline LLM-defense целиком (детекторы,
    # LLM-классификатор, security-часть промпта); гранулярность для
    # исследовательских прогонов — в configs/security.yaml, не здесь.
    llm_defense_enabled: bool = True

    # MCP encryption
    mcp_encryption_key: str = ""

    # Redis (trace storage for feedback persistence)
    redis_url: str = "redis://localhost:6379/0"

    # SIEM (security event emission)
    # Операционный тумблер: гасит только эмиссию security-событий в Redis
    # Stream из этого процесса. Не гасит контейнеры siem-service/siem-db
    # (COMPOSE_PROFILES) и не гасит UI (VITE_SIEM_ENABLED). Читается один раз
    # в lifespan — переключение требует рестарта контейнера.
    siem_enabled: bool = True

    # Operational knobs — tune without rebuild (D-ERR-9, D-ERR-11)
    redis_socket_timeout: float = 5.0
    redis_socket_connect_timeout: float = 5.0
    db_statement_timeout_seconds: int = 120
    llm_guard_timeout_seconds: float = 45
    llm_summarizer_timeout_seconds: float = 300
    llm_max_retries: int = 2
    llm_image_timeout_seconds: float = 120
    llm_title_timeout_seconds: float = 20
    mcp_timeout_seconds: int = 30
    pdf_conversion_timeout_seconds: int = 30

    # NoDecode: иначе pydantic-settings декодирует list[str] из env как JSON
    # ещё до field validator'а
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @property
    def langgraph_database_url(self) -> str:
        """PostgreSQL URL for LangGraph (without +psycopg dialect, with libpq timeout params).

        Injects ``statement_timeout`` and ``connect_timeout`` via libpq query
        parameters — the only mechanism that reaches both AsyncPostgresSaver and
        AsyncPostgresStore (neither accepts connection-kwargs directly).
        """
        base = self.database_url.replace("+psycopg", "")
        statement_timeout_ms = self.db_statement_timeout_seconds * 1000
        connect_timeout_s = int(self.redis_socket_connect_timeout)
        params = urlencode(
            {
                "options": f"-c statement_timeout={statement_timeout_ms}",
                "connect_timeout": connect_timeout_s,
            },
            quote_via=quote,
        )
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}{params}"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        # CSV, не JSON: .env шелл-сорсится (Makefile LOAD_ENV), JSON-список
        # с кавычками такой загрузки не переживает.
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
