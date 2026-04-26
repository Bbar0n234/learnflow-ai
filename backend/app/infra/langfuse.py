from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING

import structlog
from langfuse import Langfuse, get_client

if TYPE_CHECKING:
    from langfuse.api import Model

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
    """Idempotently sync Langfuse model definitions for cost tracking.

    Re-seeds when ``configs/pricing.yaml`` adds new price keys (e.g.
    ``output_reasoning``): if a managed model already exists with a different
    ``prices`` payload, delete and recreate. Idempotent on repeated startups
    when prices are unchanged.

    Pagination over the full Langfuse catalog (which can include 160+ built-in
    entries) is bounded by an exact-name match; we only touch our managed
    models.
    """
    if not langfuse_enabled or not models:
        return

    from langfuse.api import PricingTierInput
    from langfuse.api.commons.errors.error import Error as LangfuseError

    langfuse = get_client()
    existing_by_name = _list_managed_models(langfuse, {m.name for m in models})

    for model in models:
        tier = PricingTierInput(
            name="Standard",
            is_default=True,
            priority=0,
            conditions=[],
            prices=model.prices,
        )
        existing = existing_by_name.get(model.name)
        if existing is not None:
            if _model_prices_match(existing, model.prices):
                logger.debug("langfuse model up-to-date", model_name=model.name)
                continue
            try:
                langfuse.api.models.delete(existing.id)
                logger.info(
                    "langfuse model definition deleted for re-seed",
                    model_name=model.name,
                )
            except LangfuseError:
                logger.warning(
                    "langfuse model delete failed, attempting create anyway",
                    model_name=model.name,
                    exc_info=True,
                )

        try:
            langfuse.api.models.create(
                model_name=model.name,
                match_pattern=model.match_pattern,
                unit=model.unit,
                pricing_tiers=[tier],
            )
            logger.info(
                "langfuse model definition created",
                model_name=model.name,
                prices=list(model.prices.keys()),
            )
        except LangfuseError as exc:
            if exc.status_code == 400 and "already exists" in str(exc.body):
                logger.debug("langfuse model already exists", model_name=model.name)
            else:
                raise


def _list_managed_models(langfuse: Langfuse, names: set[str]) -> dict[str, Model]:
    """Page through Langfuse models and pick the ones we manage."""
    found: dict[str, Model] = {}
    page = 1
    limit = 100
    while True:
        resp = langfuse.api.models.list(page=page, limit=limit)
        for model in resp.data:
            if model.model_name in names and not getattr(
                model, "is_langfuse_managed", False
            ):
                found[model.model_name] = model
        meta = getattr(resp, "meta", None)
        total_pages = getattr(meta, "total_pages", page) if meta is not None else page
        if page >= total_pages:
            return found
        page += 1


def _model_prices_match(existing: Model, expected: dict[str, float]) -> bool:
    """Compare default-tier prices on an existing model against expected dict."""
    tiers = getattr(existing, "pricing_tiers", None) or []
    default_tier = next(
        (t for t in tiers if getattr(t, "is_default", False)),
        tiers[0] if tiers else None,
    )
    if default_tier is None:
        return False
    actual = getattr(default_tier, "prices", None) or {}
    if set(actual.keys()) != set(expected.keys()):
        return False
    return all(abs(float(actual[k]) - float(expected[k])) < 1e-12 for k in expected)


def shutdown_langfuse() -> None:
    """Gracefully shut down Langfuse client."""
    with contextlib.suppress(Exception):
        get_client().shutdown()
