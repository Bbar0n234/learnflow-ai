"""
Factory for creating LLM models based on configuration.
"""

import logging
from typing import Optional

from langchain_openai import ChatOpenAI

from ..config.config_manager import get_config_manager
from ..config.config_models import ModelConfig


logger = logging.getLogger(__name__)


class ModelFactory:
    """Factory for creating configured LLM models."""

    def __init__(self, api_key: str, config_manager=None):
        """
        Initialize the model factory.

        Args:
            api_key: OpenAI API key
            config_manager: Optional config manager, uses global instance if None
        """
        self.api_key = api_key
        self.config_manager = config_manager or get_config_manager()

    def create_model(self, config: ModelConfig) -> ChatOpenAI:
        """
        Create a ChatOpenAI model based on configuration.

        Args:
            config: Model configuration

        Returns:
            Configured ChatOpenAI instance
        """
        if config.provider != "openai":
            raise ValueError(f"Unsupported provider: {config.provider}")

        # Build model parameters
        model_params = {
            "model": config.model_name,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "openai_api_key": self.api_key,
        }

        # Add optional parameters if specified
        if config.top_p is not None:
            model_params["top_p"] = config.top_p
        if config.frequency_penalty is not None:
            model_params["frequency_penalty"] = config.frequency_penalty
        if config.presence_penalty is not None:
            model_params["presence_penalty"] = config.presence_penalty

        logger.debug(
            f"Creating model with config: {config.model_name}, temp={config.temperature}, max_tokens={config.max_tokens}"
        )

        return ChatOpenAI(**model_params)

    def create_model_for_node(self, node_name: str) -> ChatOpenAI:
        """
        Create a model for a specific workflow node.

        Args:
            node_name: Name of the workflow node

        Returns:
            Configured ChatOpenAI instance for the node
        """
        config = self.config_manager.get_model_config(node_name)

        if not self.config_manager.has_node_config(node_name):
            logger.warning(
                f"No specific configuration found for node '{node_name}', using default configuration"
            )

        return self.create_model(config)

    def create_default_model(self) -> ChatOpenAI:
        """
        Create a model using default configuration.

        Returns:
            Configured ChatOpenAI instance with default settings
        """
        config = self.config_manager.get_default_model_config()
        return self.create_model(config)


# Global model factory instance
_model_factory: Optional[ModelFactory] = None


def get_model_factory() -> Optional[ModelFactory]:
    """
    Get the global model factory instance.

    Returns:
        ModelFactory instance or None if not initialized
    """
    return _model_factory


def initialize_model_factory(api_key: str, config_manager=None) -> ModelFactory:
    """
    Initialize the global model factory.

    Args:
        api_key: OpenAI API key
        config_manager: Optional config manager

    Returns:
        ModelFactory instance
    """
    global _model_factory
    _model_factory = ModelFactory(api_key, config_manager)
    return _model_factory


def create_model_for_node(node_name: str, api_key: Optional[str] = None) -> ChatOpenAI:
    """
    Convenience function to create a model for a node using global factory.

    Args:
        node_name: Name of the workflow node
        api_key: Optional API key, uses global factory if None

    Returns:
        Configured ChatOpenAI instance
    """
    if api_key:
        # Create temporary factory for this call
        factory = ModelFactory(api_key)
        return factory.create_model_for_node(node_name)

    # Use global factory
    factory = get_model_factory()
    if not factory:
        raise RuntimeError(
            "Model factory not initialized. Call initialize_model_factory() first."
        )

    return factory.create_model_for_node(node_name)
