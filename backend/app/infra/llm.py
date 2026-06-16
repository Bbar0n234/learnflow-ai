from __future__ import annotations

from typing import TYPE_CHECKING, Any

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

if TYPE_CHECKING:
    # Annotation-only: runtime import of app.agent.* here closes the
    # app.infra.llm ↔ app.agent import cycle (classifier imports extract_usage).
    from app.agent.config import ResolvedModelConfig, SummarizationConfig
    from app.agent.security.types import SecurityConfig
    from app.config import Settings


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI with reasoning extraction for OpenRouter-compatible providers.

    Extracts `reasoning` from non-standard response fields into
    AIMessage.additional_kwargs["reasoning"] for both invoke and streaming.
    """

    # --- Non-streaming path ---
    def _create_chat_result(
        self,
        response: dict[str, Any] | openai.BaseModel,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(exclude_none=True)
        )
        choices = response_dict.get("choices") or []
        for gen, choice in zip(result.generations, choices, strict=False):
            if not isinstance(gen.message, AIMessage):
                continue
            msg_payload = choice.get("message") or {}
            reasoning = msg_payload.get("reasoning")
            if reasoning is not None:
                gen.message.additional_kwargs["reasoning"] = reasoning
        return result

    # --- Streaming path ---
    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None

        choices = chunk.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning")
            if reasoning and isinstance(gen_chunk.message, AIMessageChunk):
                gen_chunk.message.additional_kwargs["reasoning"] = reasoning

        return gen_chunk


def _build_chat_model(
    settings: Settings,
    model: str,
    extra_body: dict[str, Any] | None,
    *,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> BaseChatModel:
    """Construct the project's chat model.

    ``ReasoningChatOpenAI`` is used unconditionally: it is a safe superset of
    ``ChatOpenAI`` (reasoning extraction is a no-op when the provider returns no
    ``reasoning`` field), so every model in the project surfaces reasoning when
    available without per-callsite branching. See conventions.md § Reasoning LLMs.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if temperature is not None:
        kwargs["temperature"] = temperature
    if extra_body:
        kwargs["extra_body"] = extra_body
    return ReasoningChatOpenAI(**kwargs)


def create_summarization_llm(
    settings: Settings, config: SummarizationConfig
) -> BaseChatModel:
    return _build_chat_model(
        settings,
        config.model,
        config.extra_body or None,
        max_tokens=config.max_summary_tokens,
    )


def create_llm_from_config(
    settings: Settings, model_config: ResolvedModelConfig
) -> BaseChatModel:
    """Create LLM from a resolved model configuration (per-request)."""
    return _build_chat_model(settings, model_config.model, model_config.extra_body)


def create_guard_llm(
    settings: Settings, security_config: SecurityConfig
) -> BaseChatModel:
    """Create LLM for the security guard classifier."""
    cfg = security_config.llm_classifier
    return _build_chat_model(
        settings,
        cfg.model,
        cfg.extra_body.as_dict() or None,
        temperature=cfg.temperature,
    )


def extract_usage(response: BaseMessage) -> dict[str, Any] | None:
    """Extract usage tokens from an LLM response in a canonical shape.

    Priority order: ``response.usage_metadata`` (LangChain canonical) →
    ``response.response_metadata.token_usage`` / ``usage`` (provider-specific
    fallback). Returns ``None`` when no usage data is available.
    """
    usage = getattr(response, "usage_metadata", None)
    if usage:
        return dict(usage)

    metadata = getattr(response, "response_metadata", None) or {}
    if isinstance(metadata, dict):
        fallback = metadata.get("token_usage") or metadata.get("usage")
        if fallback:
            return dict(fallback)
    return None


def normalize_usage_for_langfuse(usage: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize LangChain / OpenAI usage shape into Langfuse ``usage_details``.

    Langfuse v4 ``usage_details`` keys must match the pricing keys defined in
    the model's ``PricingTierInput.prices`` exactly (see ``configs/pricing.yaml``):

    ``input`` (prompt tokens), ``output`` (completion tokens), ``total``,
    ``output_reasoning`` (reasoning tokens), ``input_cache_read`` (cached
    prompt tokens).

    Accepts both LangChain canonical (``input_tokens``/``output_tokens`` +
    nested ``*_token_details``) and OpenAI-style (``prompt_tokens`` etc.)
    sources to stay tolerant to provider drift.
    """
    if not usage:
        return {}
    out: dict[str, Any] = {}

    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    total_tokens = usage.get("total_tokens")

    if input_tokens is not None:
        out["input"] = input_tokens
    if output_tokens is not None:
        out["output"] = output_tokens
    if total_tokens is not None:
        out["total"] = total_tokens

    output_details = usage.get("output_token_details") or usage.get(
        "completion_tokens_details"
    )
    if isinstance(output_details, dict):
        reasoning = output_details.get("reasoning") or output_details.get(
            "reasoning_tokens"
        )
        if reasoning:
            out["output_reasoning"] = reasoning

    input_details = usage.get("input_token_details") or usage.get(
        "prompt_tokens_details"
    )
    if isinstance(input_details, dict):
        cached = input_details.get("cache_read") or input_details.get("cached_tokens")
        if cached:
            out["input_cache_read"] = cached

    return out
