"""
Pydantic models for LLM configuration management.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """Configuration for a single LLM model."""

    provider: str = Field(default="openai", description="LLM provider")
    model_name: str = Field(description="Model name")
    temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Temperature for generation"
    )
    max_tokens: int = Field(default=4000, gt=0, description="Maximum number of tokens")
    top_p: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Top-p parameter"
    )
    frequency_penalty: Optional[float] = Field(
        default=None, ge=-2.0, le=2.0, description="Frequency penalty"
    )
    presence_penalty: Optional[float] = Field(
        default=None, ge=-2.0, le=2.0, description="Presence penalty"
    )


class LLMModelsConfig(BaseModel):
    """Configuration for all LLM models."""

    default: ModelConfig = Field(description="Default model configuration")
    nodes: Dict[str, ModelConfig] = Field(
        default_factory=dict, description="Per-node model configurations"
    )


class GraphConfig(BaseModel):
    """Complete graph configuration including models and other settings."""

    models: LLMModelsConfig = Field(description="LLM models configuration")
    graph_config: Optional[Dict] = Field(
        default=None, description="Additional graph configuration"
    )
