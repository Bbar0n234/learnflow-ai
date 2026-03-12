from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.agent.config import AgentConfig, SummarizationConfig
from app.config import Settings


def create_llm(settings: Settings, agent_config: AgentConfig) -> BaseChatModel:
    return ChatOpenAI(  # type: ignore[call-arg]
        model=agent_config.llm.model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )


def create_summarization_llm(
    settings: Settings, config: SummarizationConfig
) -> BaseChatModel:
    return ChatOpenAI(  # type: ignore[call-arg]
        model=config.model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        max_tokens=config.max_summary_tokens,
    )
