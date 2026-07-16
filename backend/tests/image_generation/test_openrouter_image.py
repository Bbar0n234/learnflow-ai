"""Unit tests for the OpenRouter Image API helper (T1.4).

The helper (``app.infra.image_generation.generate_image``) is a thin wrapper over
``POST {llm_base_url}/images`` with bare ``httpx``. We stub the wire with
``httpx.MockTransport`` (no network, no key) and assert the observable contract:
the request it sends and the result/exception it derives from a response. Error
mapping is a critical path (provider failures -> typed ``UpstreamUnavailableError``
with the right HTTP status), so it gets negative cases per status class.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from app.agent.config import ImageConfig
from app.infra.image_generation import generate_image
from app.services.exceptions import UpstreamUnavailableError

pytestmark = pytest.mark.unit

_PNG = b"\x89PNG\r\n\x1a\n binary payload"
_B64 = base64.b64encode(_PNG).decode()


def _settings() -> Any:
    # A structural stand-in for Settings — the helper only reads three attrs.
    return SimpleNamespace(
        llm_base_url="https://openrouter.test/api/v1",
        llm_api_key="test-key",
        llm_image_timeout_seconds=30,
    )


def _install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Route the helper's ``httpx.AsyncClient`` through a MockTransport."""
    real_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(
        "app.infra.image_generation.httpx.AsyncClient", _factory, raising=True
    )


def _ok_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": [{"b64_json": _B64, "media_type": "image/png"}],
            "usage": {"cost": 0.067},
        },
    )


async def test_generate_image_decodes_bytes_media_type_and_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transport(monkeypatch, _ok_response)

    result = await generate_image(_settings(), ImageConfig(model="m"), prompt="a cat")

    assert result.data == _PNG
    assert result.media_type == "image/png"
    assert result.cost == 0.067


async def test_generate_image_sends_expected_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return _ok_response(request)

    _install_transport(monkeypatch, handler)

    await generate_image(
        _settings(),
        ImageConfig(model="google/gemini-3.1-flash-image", params={"safety": "off"}),
        prompt="a coherent paragraph",
        aspect_ratio="16:9",
        resolution="2K",
    )

    assert captured["url"] == "https://openrouter.test/api/v1/images"
    assert captured["auth"] == "Bearer test-key"
    # model + prompt + optional agent args + operator ``params`` all reach the
    # provider in the request body.
    assert captured["body"] == {
        "model": "google/gemini-3.1-flash-image",
        "prompt": "a coherent paragraph",
        "aspect_ratio": "16:9",
        "resolution": "2K",
        "safety": "off",
    }


async def test_generate_image_omits_unset_optional_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ok_response(request)

    _install_transport(monkeypatch, handler)

    await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    # Unset aspect_ratio/resolution are not sent (provider applies its defaults).
    assert captured["body"] == {"model": "m", "prompt": "p"}


async def test_generate_image_missing_cost_yields_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"b64_json": _B64, "media_type": "image/png"}]}
        )

    _install_transport(monkeypatch, handler)

    result = await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    assert result.cost is None


@pytest.mark.parametrize("status", [400, 429, 500, 502])
async def test_generate_image_non_2xx_maps_to_502_failed(
    monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"error": "nope"})

    _install_transport(monkeypatch, handler)

    with pytest.raises(UpstreamUnavailableError) as exc:
        await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    assert exc.value.status == 502
    assert exc.value.code == "image-generation-failed"


async def test_generate_image_timeout_maps_to_503_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _install_transport(monkeypatch, handler)

    with pytest.raises(UpstreamUnavailableError) as exc:
        await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    assert exc.value.status == 503
    assert exc.value.code == "image-generation-unavailable"


async def test_generate_image_network_error_maps_to_503_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    _install_transport(monkeypatch, handler)

    with pytest.raises(UpstreamUnavailableError) as exc:
        await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    assert exc.value.status == 503
    assert exc.value.code == "image-generation-unavailable"


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},  # empty data array
        {"usage": {"cost": 1}},  # no data key at all
        {"data": [{"media_type": "image/png"}]},  # missing b64_json
        {"data": [{"b64_json": _B64}]},  # missing media_type
        # Keys present but values are null/wrong-type/empty: the provider
        # returned the fields, just not a usable string. Type-validated the
        # same as absent keys (would otherwise be an unclassified TypeError).
        {"data": [{"b64_json": None, "media_type": "image/png"}]},  # b64_json null
        {"data": [{"b64_json": _B64, "media_type": None}]},  # media_type null
        {"data": [{"b64_json": "", "media_type": "image/png"}]},  # b64_json empty
        {"data": [{"b64_json": _B64, "media_type": ""}]},  # media_type empty
        {"data": [{"b64_json": 123, "media_type": "image/png"}]},  # b64_json non-str
    ],
)
async def test_generate_image_malformed_2xx_maps_to_502_malformed(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _install_transport(monkeypatch, handler)

    with pytest.raises(UpstreamUnavailableError) as exc:
        await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    assert exc.value.status == 502
    assert exc.value.code == "image-generation-malformed-response"


async def test_generate_image_invalid_base64_maps_to_502_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [{"b64_json": "not!valid!base64", "media_type": "image/png"}]
            },
        )

    _install_transport(monkeypatch, handler)

    with pytest.raises(UpstreamUnavailableError) as exc:
        await generate_image(_settings(), ImageConfig(model="m"), prompt="p")

    assert exc.value.status == 502
    assert exc.value.code == "image-generation-malformed-response"
