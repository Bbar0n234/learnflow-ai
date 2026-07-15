from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import Settings
from app.services.exceptions import UpstreamUnavailableError

if TYPE_CHECKING:
    # Annotation-only: runtime import of app.agent.* here closes the
    # app.infra.image_generation ↔ app.agent import cycle (app.agent.__init__
    # → app.agent.runner pulls in app.infra.llm before app.agent.config would
    # finish initializing) — same rationale as app.infra.llm.
    from app.agent.config import ImageConfig

logger = structlog.get_logger()


@dataclass(frozen=True)
class ImageGenerationResult:
    """Decoded result of a successful OpenRouter image generation call."""

    data: bytes
    media_type: str
    cost: float | None


async def generate_image(
    settings: Settings,
    image_config: ImageConfig,
    *,
    prompt: str,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
) -> ImageGenerationResult:
    """Call OpenRouter's Image API (``POST {llm_base_url}/images``).

    Billing is all-or-nothing (OpenRouter side): a failed or cancelled
    generation is not charged. This function mirrors that on our side — it
    either returns a fully decoded result or raises, with no partial state
    for the caller to reason about (no artifact/blob is written on error).

    Args:
        settings: provides ``llm_base_url``, ``llm_api_key``, and
            ``llm_image_timeout_seconds``.
        image_config: ``image`` section of ``agent.yaml`` (``model`` +
            default ``params``, merged into the request body as-is —
            ``extra_body`` pattern).
        prompt: text description of the desired image.
        aspect_ratio: optional OpenRouter aspect ratio tier (e.g. ``"16:9"``).
        resolution: optional OpenRouter resolution tier (e.g. ``"1K"``).

    Raises:
        UpstreamUnavailableError: non-2xx response (502), network/timeout
            failure (503), or a response body missing the expected
            ``data[0].b64_json`` / ``media_type`` fields (502).
    """
    body: dict[str, Any] = {"model": image_config.model, "prompt": prompt}
    if aspect_ratio is not None:
        body["aspect_ratio"] = aspect_ratio
    if resolution is not None:
        body["resolution"] = resolution
    body.update(image_config.params)

    url = f"{settings.llm_base_url}/images"
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    try:
        async with httpx.AsyncClient(
            timeout=settings.llm_image_timeout_seconds
        ) as client:
            response = await client.post(url, json=body, headers=headers)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning(
            "image generation upstream error",
            status_code=e.response.status_code,
            model=image_config.model,
            exc_info=True,
        )
        raise UpstreamUnavailableError(
            code="image-generation-failed",
            status=502,
            detail="Image generation failed",
        ) from e
    except (httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError) as e:
        logger.warning(
            "image generation request error", model=image_config.model, exc_info=True
        )
        raise UpstreamUnavailableError(
            code="image-generation-unavailable",
            status=503,
            detail="Image generation service unavailable",
        ) from e

    try:
        payload = response.json()
        image_entry = payload["data"][0]
        b64_json = image_entry["b64_json"]
        media_type = image_entry["media_type"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        logger.warning(
            "image generation malformed response",
            model=image_config.model,
            exc_info=True,
        )
        raise UpstreamUnavailableError(
            code="image-generation-malformed-response",
            status=502,
            detail="Image generation returned an unexpected response",
        ) from e

    try:
        image_bytes = base64.b64decode(b64_json, validate=True)
    except binascii.Error as e:
        logger.warning(
            "image generation invalid base64", model=image_config.model, exc_info=True
        )
        raise UpstreamUnavailableError(
            code="image-generation-malformed-response",
            status=502,
            detail="Image generation returned an unexpected response",
        ) from e

    usage = payload.get("usage") or {}
    cost = usage.get("cost")

    return ImageGenerationResult(data=image_bytes, media_type=media_type, cost=cost)
