"""Executor service configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Executor service settings.

    No secrets, no required fields — access to the executor is controlled by
    the `exec` network segment, not by application-level auth (design-brief
    § Executor). The mount set of the sandbox is a security invariant and
    lives in code (`executor.sandbox`), not here (§ Что попадает в env).
    """

    model_config = SettingsConfigDict(env_prefix="EXECUTOR_")

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
    # without userns). Never set in compose; every use logs a WARNING.
    sandbox_enabled: bool = True
