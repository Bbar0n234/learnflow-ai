"""External: pricing.yaml vs the live OpenRouter catalog.

Marker ``external`` (registered in ``pyproject.toml``) — hits
``GET {Settings.llm_base_url}/models``, OpenRouter's public catalog endpoint
(no API key required). Runs in the default ``make test`` sweep per design-brief
§ Тесты, but degrades gracefully when the network is unavailable (sandboxed
CI, offline dev box): any connection failure or non-200 response skips the
whole module rather than failing it — these tests guard against real
repricing/deprecation on OpenRouter, not against reachability.

Price-drift tolerance is ±10% (architect decision, design-brief § Тесты):
multi-provider models aggregate prices across providers and fluctuate
intra-day; a hard equality assert would flake on data noise, not catch real
repricing.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from app.agent.config import load_agent_config, load_pricing_config
from app.agent.security.config import load_security_config
from app.config import Settings
from pydantic import ValidationError

PRICE_DRIFT_TOLERANCE = 0.10
MIN_WHITELIST_CONTEXT = 100_000

# pricing.yaml field -> OpenRouter catalog `pricing` field.
_PRICE_FIELD_MAP = {
    "input": "prompt",
    "output": "completion",
    "input_cache_read": "input_cache_read",
}


def _active_model_slugs() -> set[str]:
    agent = load_agent_config()
    security = load_security_config()
    slugs = {agent.llm.model, security.llm_classifier.model}
    if agent.summarization is not None:
        slugs.add(agent.summarization.model)
    if agent.subagents is not None:
        slugs.add(agent.subagents.llm.model)
    slugs.update(m.name for m in agent.available_models)
    return slugs


@pytest.fixture(scope="module")
def catalog() -> dict[str, dict[str, Any]]:
    """Fetch the live OpenRouter catalog once; skip the module on any network trouble."""
    try:
        settings = Settings()
    except ValidationError as exc:
        pytest.skip(f"Settings недоступны (нет env): {exc}")

    url = f"{settings.llm_base_url.rstrip('/')}/models"
    try:
        response = httpx.get(url, timeout=10.0)
    except httpx.RequestError as exc:
        pytest.skip(f"OpenRouter catalog unreachable ({url}): {exc}")

    if response.status_code != 200:
        pytest.skip(
            f"OpenRouter catalog returned HTTP {response.status_code} for {url}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        pytest.skip(f"OpenRouter catalog returned a non-JSON payload: {exc}")

    return {entry["id"]: entry for entry in payload.get("data", []) if "id" in entry}


def _pricing_entry_for(slug: str, pricing_models: list[Any]) -> Any | None:
    return next(
        (entry for entry in pricing_models if re.match(entry.match_pattern, slug)),
        None,
    )


@pytest.mark.external
def test_active_model_prices_within_drift_tolerance(
    catalog: dict[str, dict[str, Any]],
) -> None:
    pricing_models = load_pricing_config().models
    diffs: list[str] = []

    for slug in sorted(_active_model_slugs()):
        live = catalog.get(slug)
        if live is None:
            # Presence is asserted by the whitelist-availability test; without a
            # live entry there is nothing to diff prices against here.
            continue

        entry = _pricing_entry_for(slug, pricing_models)
        if entry is None:
            # Covered (and would already fail) by the unit consistency test;
            # skip re-asserting it here to keep this test single-purpose.
            continue

        live_prices = live.get("pricing", {})
        for yaml_field, catalog_field in _PRICE_FIELD_MAP.items():
            yaml_value = entry.prices.get(yaml_field)
            live_raw = live_prices.get(catalog_field)

            if live_raw is None:
                # Catalog omits some zero-cost fields entirely (e.g. no
                # cache-read pricing published at all). Only fine to skip the
                # comparison when pricing.yaml agrees the price is zero.
                if yaml_value in (None, 0, 0.0):
                    continue
                diffs.append(
                    f"{slug}.{yaml_field}: pricing.yaml={yaml_value} but catalog "
                    f"has no '{catalog_field}' field"
                )
                continue

            live_value = float(live_raw)
            if yaml_value is None:
                diffs.append(
                    f"{slug}.{yaml_field}: missing in pricing.yaml, live={live_value}"
                )
                continue

            if live_value == 0.0 and yaml_value == 0.0:
                continue

            baseline = live_value if live_value != 0.0 else yaml_value
            drift = abs(yaml_value - live_value) / baseline if baseline else 0.0
            if drift > PRICE_DRIFT_TOLERANCE:
                diffs.append(
                    f"{slug}.{yaml_field}: pricing.yaml={yaml_value} live={live_value} "
                    f"drift={drift:.1%} (tolerance {PRICE_DRIFT_TOLERANCE:.0%})"
                )

    assert not diffs, "Price drift beyond tolerance:\n" + "\n".join(diffs)


@pytest.mark.external
def test_whitelist_models_available_with_tools_and_context(
    catalog: dict[str, dict[str, Any]],
) -> None:
    whitelist = [m.name for m in load_agent_config().available_models]
    problems: list[str] = []

    for slug in whitelist:
        live = catalog.get(slug)
        if live is None:
            problems.append(f"{slug}: not present in the OpenRouter catalog")
            continue

        supported = live.get("supported_parameters") or []
        if "tools" not in supported:
            problems.append(
                f"{slug}: 'tools' not in supported_parameters ({supported})"
            )

        context_length = live.get("context_length") or 0
        if context_length < MIN_WHITELIST_CONTEXT:
            problems.append(
                f"{slug}: context_length={context_length} < {MIN_WHITELIST_CONTEXT}"
            )

    assert not problems, "Whitelist availability issues:\n" + "\n".join(problems)
