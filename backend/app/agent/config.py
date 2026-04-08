from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from app.agent.security.types import SecurityConfig


class LLMConfig(BaseModel):
    model: str
    extra_body: dict[str, Any] = {}


class ContextConfig(BaseModel):
    max_tokens: int
    compaction_threshold_ratio: float = 0.75
    recent_messages_to_keep: int = 10


class SummarizationConfig(BaseModel):
    model: str
    max_summary_tokens: int = 500


class MCPServerConfig(BaseModel):
    enabled: bool = True
    transport: str  # "http", "sse", "stdio"
    url: str | None = None
    api_key_env: str | None = None
    command: str | None = None
    args: list[str] | None = None
    allowed_tools: list[str] = []


class ModelDefinitionConfig(BaseModel):
    name: str
    match_pattern: str
    unit: str = "TOKENS"
    prices: dict[str, float] = {}


class AvailableModel(BaseModel):
    name: str
    display_name: str


class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    summarization: SummarizationConfig | None = None
    security: SecurityConfig | None = None
    mcp_servers: dict[str, MCPServerConfig] = {}
    models: list[ModelDefinitionConfig] = []
    available_models: list[AvailableModel] = []


@dataclass
class ResolvedModelConfig:
    model: str
    extra_body: dict[str, Any] | None
    source: str  # "thread"|"project"|"user"|"langfuse"|"config"


def load_agent_config(path: Path | None = None) -> AgentConfig:
    if path is None:
        # configs/agent.yaml at repo root
        path = Path(__file__).resolve().parents[3] / "configs" / "agent.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return AgentConfig(**data)
