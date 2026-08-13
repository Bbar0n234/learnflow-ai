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

    # Workspace (file layer, ADR-032) — two allowed roots for agent/REST path
    # resolution. Defaults are the container mount points (docker-compose);
    # local dev (host mode, make dev) overrides both in .env.local.
    workspaces_root: str = "/workspaces"
    skills_root: str = "/skills"
    # read_file: truncation limit, mirrors text_limits.truncate's UX
    # (truncation + a flag) but is an operational knob, not the fixed
    # wire-truncation business invariant text_limits carries.
    workspace_read_limit_chars: int = 50_000
    # Before-copy limits for the artifacts/ diff snapshot taken around a job
    # (execute_code/run_command): per-file and total-per-job. Either one
    # being exceeded drops the line-diff for that path (kind still reported,
    # just diff=None) rather than holding unbounded content in memory for
    # the duration of a job.
    workspace_diff_file_limit_bytes: int = 1_000_000
    workspace_diff_total_limit_bytes: int = 10_000_000
    # POST /uploads size ceiling.
    upload_max_size_bytes: int = 20_000_000

    # Executor (execute_code / run_command, ADR-031) — client-side knobs of
    # the httpx wrapper around the executor service. The executor's own
    # EXECUTOR_* Settings (services/executor) are the authority on the
    # numbers referenced below.
    executor_base_url: str = "http://executor:8002"
    # Shared secret presented to the executor on every POST /jobs
    # (`Authorization: Bearer`). Required, no default (conventions.md
    # § Секреты и fail-fast) — the same value must be set on the executor
    # container as its own EXECUTOR_AUTH_TOKEN.
    executor_auth_token: str
    # Job deadline sent to the executor. Must stay ≤ EXECUTOR_MAX_TIMEOUT_SECONDS
    # (300 — the executor's clamp ceiling): going over it just means the
    # executor silently clamps to its own ceiling instead of respecting this
    # value, which would desync the two ends of the kill contract.
    executor_job_timeout_seconds: int = 60
    # Added on top of the job deadline for the httpx client timeout. Must
    # stay ≥ EXECUTOR_KILL_GRACE_SECONDS (5s — the pause between the
    # executor's SIGTERM and SIGKILL on a timed-out job) plus slack: the
    # executor's response to a timed-out job only arrives after
    # deadline + kill-grace, so a smaller margin would turn every job timeout
    # into a false "runtime unavailable" from the client's point of view.
    executor_client_timeout_grace_seconds: int = 10

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
