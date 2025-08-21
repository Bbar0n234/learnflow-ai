"""
Graph configuration manager for loading and managing LLM model configurations.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from .config_models import GraphConfig, ModelConfig


logger = logging.getLogger(__name__)


class GraphConfigManager:
    """Manager for loading and accessing graph configuration."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the configuration manager.

        Args:
            config_path: Path to the graph.yaml configuration file.
                        If None, defaults to configs/graph.yaml
        """
        self.config_path = config_path or "configs/graph.yaml"
        self._config: Optional[GraphConfig] = None
        self._load_config()

    def _load_config(self) -> None:
        """Load and validate configuration from YAML file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                raise FileNotFoundError(
                    f"Configuration file not found: {self.config_path}"
                )

            with open(config_file, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)

            if not yaml_data:
                raise ValueError(f"Configuration file is empty: {self.config_path}")

            self._config = GraphConfig(**yaml_data)
            logger.info(f"Successfully loaded configuration from {self.config_path}")

        except FileNotFoundError as e:
            logger.error(f"Configuration file not found: {e}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in configuration file {self.config_path}: {e}")
            raise
        except ValidationError as e:
            logger.error(f"Configuration validation failed for {self.config_path}: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error loading configuration from {self.config_path}: {e}"
            )
            raise

    def reload_config(self) -> None:
        """Reload configuration from file."""
        logger.info(f"Reloading configuration from {self.config_path}")
        self._load_config()

    def get_model_config(self, node_name: str) -> ModelConfig:
        """
        Get model configuration for a specific node.

        Args:
            node_name: Name of the workflow node

        Returns:
            ModelConfig for the node, or default config if node-specific config not found
        """
        if not self._config:
            raise RuntimeError("Configuration not loaded")

        # Try to get node-specific configuration
        node_config = self._config.models.nodes.get(node_name)
        if node_config:
            logger.debug(f"Using node-specific configuration for {node_name}")
            return node_config

        # Fall back to default configuration
        logger.debug(f"Using default configuration for {node_name}")
        return self._config.models.default

    def get_default_model_config(self) -> ModelConfig:
        """
        Get default model configuration.

        Returns:
            Default ModelConfig
        """
        if not self._config:
            raise RuntimeError("Configuration not loaded")

        return self._config.models.default

    def get_full_config(self) -> GraphConfig:
        """
        Get the complete graph configuration.

        Returns:
            Complete GraphConfig object
        """
        if not self._config:
            raise RuntimeError("Configuration not loaded")

        return self._config

    def has_node_config(self, node_name: str) -> bool:
        """
        Check if a specific node has its own configuration.

        Args:
            node_name: Name of the workflow node

        Returns:
            True if node has specific configuration, False otherwise
        """
        if not self._config:
            return False

        return node_name in self._config.models.nodes


# Global configuration manager instance
_config_manager: Optional[GraphConfigManager] = None


def get_config_manager() -> GraphConfigManager:
    """
    Get the global configuration manager instance.

    Returns:
        GraphConfigManager instance
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = GraphConfigManager()
    return _config_manager


def initialize_config_manager(config_path: Optional[str] = None) -> GraphConfigManager:
    """
    Initialize the global configuration manager with a specific config path.

    Args:
        config_path: Path to the configuration file

    Returns:
        GraphConfigManager instance
    """
    global _config_manager
    _config_manager = GraphConfigManager(config_path)
    return _config_manager
