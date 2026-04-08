from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import structlog
from langfuse import Langfuse, get_client

if TYPE_CHECKING:
    from app.agent.config import ModelDefinitionConfig

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


def ensure_security_score_config() -> None:
    """Idempotently create security_verdict score config (CATEGORICAL)."""
    if not langfuse_enabled:
        return

    langfuse = get_client()
    configs = langfuse.api.score_configs.get(limit=100)
    exists = any(
        c.name == "security_verdict" and c.data_type == "CATEGORICAL"
        for c in configs.data
    )
    if not exists:
        langfuse.api.score_configs.create(
            name="security_verdict",
            data_type="CATEGORICAL",
            description="Security guard verdict (CLEAN, SUSPICIOUS, INJECTION)",
            categories=[
                {"label": "CLEAN", "value": 0},
                {"label": "SUSPICIOUS", "value": 1},
                {"label": "INJECTION", "value": 2},
            ],
        )
        logger.info("langfuse score config created", name="security_verdict")


def ensure_model_definitions(models: list[ModelDefinitionConfig]) -> None:
    """Idempotently create Langfuse model definitions for cost tracking.

    Uses try/create per model: Langfuse returns 400 if model_name already
    exists, which we treat as a no-op. This avoids paginating the full
    built-in model catalog (160+ entries) just to check existence.
    """
    if not langfuse_enabled or not models:
        return

    from langfuse.api import PricingTierInput
    from langfuse.api.commons.errors.error import Error as LangfuseError

    langfuse = get_client()

    for model in models:
        tier = PricingTierInput(
            name="Standard",
            is_default=True,
            priority=0,
            conditions=[],
            prices=model.prices,
        )
        try:
            langfuse.api.models.create(
                model_name=model.name,
                match_pattern=model.match_pattern,
                unit=model.unit,
                pricing_tiers=[tier],
            )
            logger.info("langfuse model definition created", model_name=model.name)
        except LangfuseError as exc:
            if exc.status_code == 400 and "already exists" in str(exc.body):
                logger.debug("langfuse model already exists", model_name=model.name)
            else:
                raise


def shutdown_langfuse() -> None:
    """Gracefully shut down Langfuse client."""
    with contextlib.suppress(Exception):
        get_client().shutdown()
