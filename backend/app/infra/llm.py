from typing import Any

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

from app.agent.config import AgentConfig, ResolvedModelConfig, SummarizationConfig
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


def create_llm(settings: Settings, agent_config: AgentConfig) -> BaseChatModel:
    extra_body = agent_config.llm.extra_body
    use_reasoning = extra_body.get("include_reasoning", False) if extra_body else False
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": agent_config.llm.model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body

    return llm_class(**kwargs)


def create_summarization_llm(
    settings: Settings, config: SummarizationConfig
) -> BaseChatModel:
    extra_body = config.extra_body or {}
    use_reasoning = extra_body.get("include_reasoning", False)
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": config.model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "max_tokens": config.max_summary_tokens,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    return llm_class(**kwargs)


def create_llm_from_config(
    settings: Settings, model_config: ResolvedModelConfig
) -> BaseChatModel:
    """Create LLM from a resolved model configuration (per-request)."""
    extra_body = model_config.extra_body or {}
    use_reasoning = extra_body.get("include_reasoning", False)
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": model_config.model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body

    return llm_class(**kwargs)


def create_summarization_llm_from_prompt_config(
    settings: Settings, config: dict[str, Any]
) -> BaseChatModel:
    """Create summarization LLM from Langfuse prompt config dict."""
    extra_body = config.get("extra_body") or {}
    use_reasoning = extra_body.get("include_reasoning", False)
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": config.get("model", ""),
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "max_tokens": config.get("max_tokens", 500),
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    return llm_class(**kwargs)


def create_guard_llm(
    settings: Settings, security_config: SecurityConfig
) -> BaseChatModel:
    """Create LLM for the security guard classifier.

    When ``security_config.llm_classifier.extra_body.include_reasoning`` is
    true, uses ``ReasoningChatOpenAI`` to surface reasoning traces for
    calibration.
    """
    cfg = security_config.llm_classifier
    extra_body = cfg.extra_body.as_dict()
    use_reasoning = cfg.extra_body.include_reasoning
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": cfg.model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "temperature": cfg.temperature,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body
    return llm_class(**kwargs)


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
