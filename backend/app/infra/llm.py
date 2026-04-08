from typing import Any

import openai
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
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
    return ChatOpenAI(  # type: ignore[call-arg]
        model=config.model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_tokens=config.max_summary_tokens,
    )


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
    return ChatOpenAI(  # type: ignore[call-arg]
        model=config.get("model", ""),
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_tokens=config.get("max_tokens", 500),
    )


def create_guard_llm(
    settings: Settings, security_config: SecurityConfig
) -> BaseChatModel:
    """Create LLM for the security guard classifier (plain ChatOpenAI, no reasoning)."""
    kwargs: dict[str, Any] = {
        "model": security_config.guard_model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
        "temperature": security_config.temperature,
    }
    if security_config.guard_extra_body:
        kwargs["extra_body"] = security_config.guard_extra_body
    return ChatOpenAI(**kwargs)
