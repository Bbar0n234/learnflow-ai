"""
Pydantic models for LLM configuration management.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Configuration for OpenAI-compatible providers"""
    name: str = Field(description="Provider name (e.g., 'openai', 'openrouter')")
    base_url: Optional[str] = Field(default=None, description="Base URL for OpenAI-compatible API")
    api_key: Optional[str] = Field(default=None, description="API key reference (uses Jinja2 template)") 
    supports_structured_output: bool = Field(
        default=False, 
        description="Whether this provider supports structured output (function calling)"
    )
    default_model: Optional[str] = Field(default=None, description="Default model for this provider")


class ModelConfig(BaseModel):
    """Enhanced model configuration with provider support"""
    provider: str = Field(default="openai", description="Provider name from providers config")
    model_name: str = Field(description="Model name")
    temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Temperature for generation"
    )
    max_tokens: int = Field(default=4000, gt=0, description="Maximum number of tokens")
    
    # Optional parameters
    top_p: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Top-p parameter"
    )
    frequency_penalty: Optional[float] = Field(
        default=None, ge=-2.0, le=2.0, description="Frequency penalty"
    )
    presence_penalty: Optional[float] = Field(
        default=None, ge=-2.0, le=2.0, description="Presence penalty"
    )
    
    # Node requirements
    requires_structured_output: bool = Field(default=False, description="Node requires structured output support")


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
