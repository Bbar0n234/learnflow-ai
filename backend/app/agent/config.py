from pathlib import Path

import yaml
from pydantic import BaseModel


class LLMConfig(BaseModel):
    model: str


class ContextConfig(BaseModel):
    max_tokens: int
    compaction_threshold_ratio: float = 0.75
    recent_messages_to_keep: int = 10


class PromptConfig(BaseModel):
    system_file: str
    system_text: str = ""  # populated at load time


class SummarizationConfig(BaseModel):
    model: str
    max_summary_tokens: int = 500


class MCPServerConfig(BaseModel):
    transport: str  # "http", "sse", "stdio"
    url: str | None = None
    api_key_env: str | None = None
    command: str | None = None
    args: list[str] | None = None


class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig
    summarization: SummarizationConfig | None = None
    mcp_servers: dict[str, MCPServerConfig] = {}


def load_agent_config(path: Path | None = None) -> AgentConfig:
    if path is None:
        # configs/agent.yaml at repo root
        path = Path(__file__).resolve().parents[3] / "configs" / "agent.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    config = AgentConfig(**data)

    # Load prompt text from file
    configs_dir = path.parent
    prompt_path = configs_dir / config.prompt.system_file
    config.prompt.system_text = prompt_path.read_text(encoding="utf-8")

    return config
