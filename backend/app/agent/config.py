from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


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
    extra_body: dict[str, Any] = {}


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
    mcp_servers: dict[str, MCPServerConfig] = {}
    available_models: list[AvailableModel] = []


class PricingConfig(BaseModel):
    models: list[ModelDefinitionConfig] = []


class ErrorMessagesConfig(BaseModel):
    generic: str = "Request failed. Please try again."
    timeout: str = "Upstream service timed out. Please retry shortly."
    cancelled: str = "Request was cancelled."
    auth: str = "Authentication failed."
    upstream: str = "An upstream service is temporarily unavailable."


class PromptFragmentsConfig(BaseModel):
    headers: dict[str, str] = {}
    wrappers: dict[str, list[str]] = {}

    def wrap(self, key: str, text: str) -> str:
        pair = self.wrappers.get(key)
        if not pair or len(pair) != 2:
            return text
        open_tag, close_tag = pair
        if text.startswith(open_tag) and text.endswith(close_tag):
            return text
        return f"{open_tag}\n{text}\n{close_tag}"

    def open_close(self, key: str) -> tuple[str, str] | None:
        pair = self.wrappers.get(key)
        if not pair or len(pair) != 2:
            return None
        return pair[0], pair[1]


class PromptEntry(BaseModel):
    source: str
    keys: dict[str, str] = {}


class PromptsRegistry(BaseModel):
    prompts: dict[str, PromptEntry] = {}

    def resolve(
        self,
        name: str,
        agent_cfg: AgentConfig,
        security_cfg: Any,
    ) -> dict[str, Any]:
        entry = self.prompts.get(name)
        if entry is None:
            return {}

        roots: dict[str, Any] = {"agent": agent_cfg, "security": security_cfg}
        source_obj: Any = roots
        for part in entry.source.split("."):
            if isinstance(source_obj, dict):
                source_obj = source_obj.get(part)
            else:
                source_obj = getattr(source_obj, part, None)
            if source_obj is None:
                return {}

        resolved: dict[str, Any] = {}
        for target_key, source_attr in entry.keys.items():
            if isinstance(source_obj, dict):
                value = source_obj.get(source_attr)
            else:
                value = getattr(source_obj, source_attr, None)
            if isinstance(value, BaseModel):
                value = value.model_dump(exclude_none=True)
            resolved[target_key] = value
        return resolved


@dataclass
class ResolvedModelConfig:
    model: str
    extra_body: dict[str, Any] | None
    source: str  # "thread"|"project"|"user"|"langfuse"|"config"


def _configs_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "configs"


def load_agent_config(path: Path | None = None) -> AgentConfig:
    if path is None:
        path = _configs_dir() / "agent.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return AgentConfig(**data)


def load_pricing_config(path: Path | None = None) -> PricingConfig:
    if path is None:
        path = _configs_dir() / "pricing.yaml"
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return PricingConfig(**data)


def load_error_messages(path: Path | None = None) -> ErrorMessagesConfig:
    if path is None:
        path = _configs_dir() / "error_messages.yaml"
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return ErrorMessagesConfig(**data)


def load_prompt_fragments(path: Path | None = None) -> PromptFragmentsConfig:
    if path is None:
        path = _configs_dir() / "prompt_fragments.yaml"
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return PromptFragmentsConfig(**data)


def load_prompts_registry(path: Path | None = None) -> PromptsRegistry:
    if path is None:
        path = _configs_dir() / "prompts.yaml"
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return PromptsRegistry(**data)
