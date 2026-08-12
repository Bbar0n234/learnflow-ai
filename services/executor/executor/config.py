"""Executor service configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Executor service settings.

    The `exec` network segment is the first access barrier, but not the only
    one: `auth_token` is a shared secret the backend must present on every
    `POST /jobs` (`executor.api.auth`), so a foothold inside the segment is
    not by itself arbitrary code execution plus rw access to every project's
    workspace. The mount set of the sandbox is a security invariant and lives
    in code (`executor.sandbox`), not here (§ Что попадает в env).
    """

    model_config = SettingsConfigDict(env_prefix="EXECUTOR_")

    # Shared secret with the backend — required, no default (conventions.md
    # § Секреты и fail-fast): a default would silently degrade a deployment
    # into "anyone in the `exec` network may run code". Must hold the same
    # value as the backend's own `EXECUTOR_AUTH_TOKEN`.
    auth_token: str

    # Filesystem roots
    workspaces_root: str = "/workspaces"
    skills_root: str = "/skills"

    # Job deadline
    default_timeout_seconds: int = 60
    max_timeout_seconds: int = 300

    # Output ceiling — per stream (stdout/stderr each), guards service OOM.
    max_output_bytes: int = 262144

    # Kill escalation grace between SIGTERM and SIGKILL on deadline.
    kill_grace_seconds: int = 5

    # Logging
    log_level: str = "info"

    # Dev escape hatch — false runs the job without bwrap (for environments
    # without userns). Never set in compose. Turning it off is loud by
    # construction: an ERROR at startup (`executor.main`), a `sandbox`
    # degradation flag in `GET /health`, and a WARNING per job
    # (`executor.sandbox.build_job_argv`).
    sandbox_enabled: bool = True
