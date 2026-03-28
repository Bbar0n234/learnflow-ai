from __future__ import annotations

import contextlib
import logging

import structlog
from langfuse import Langfuse, get_client

logger = structlog.get_logger()

# Module-level flag: checked by _langfuse_observation to skip instrumentation.
langfuse_enabled = False


def init_langfuse(*, public_key: str, secret_key: str, host: str) -> None:
    """Initialize Langfuse singleton and ensure score config exists.

    After this call, get_client() returns the initialized instance.
    """
    global langfuse_enabled  # noqa: PLW0603

    # OTel context detach fails in async generators (CPython by design, PEP 525).
    # The error is harmless — suppress ERROR log from opentelemetry.context.
    logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)

    if not public_key or not secret_key:
        logger.info("langfuse disabled, keys not configured")
        return

    Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    langfuse = get_client()

    if not langfuse.auth_check():
        logger.warning("langfuse auth check failed, tracing disabled")
        return

    _ensure_score_config(langfuse)
    langfuse_enabled = True
    logger.info("langfuse initialized")


def _ensure_score_config(langfuse: Langfuse) -> None:
    """Idempotently create user-feedback score config."""
    configs = langfuse.api.score_configs.get(limit=100)
    exists = any(
        c.name == "user-feedback" and c.data_type == "BOOLEAN" for c in configs.data
    )
    if not exists:
        langfuse.api.score_configs.create(
            name="user-feedback",
            data_type="BOOLEAN",
            description="User feedback (1=like, 0=dislike)",
        )
        logger.info("langfuse score config created", name="user-feedback")


def shutdown_langfuse() -> None:
    """Gracefully shut down Langfuse client."""
    with contextlib.suppress(Exception):
        get_client().shutdown()
