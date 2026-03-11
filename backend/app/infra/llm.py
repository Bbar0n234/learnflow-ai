from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.agent.config import AgentConfig
from app.config import Settings


def create_llm(settings: Settings, agent_config: AgentConfig) -> BaseChatModel:
    return ChatOpenAI(  # type: ignore[call-arg]
        model=agent_config.llm.model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
