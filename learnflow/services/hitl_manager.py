"""HITL Manager Service for LearnFlow AI"""

from typing import Dict, Optional
import logging
from ..models.hitl_config import HITLConfig


logger = logging.getLogger(__name__)


class HITLManager:
    """Service for managing HITL configuration"""

    def __init__(self):
        """Initialize with configuration storage"""
        self._configs: Dict[str, HITLConfig] = {}  # thread_id -> config
        self._default_config: HITLConfig = HITLConfig()
        logger.info("HITLManager initialized with default config")

    def is_enabled(self, node_name: str, thread_id: str) -> bool:
        """
        Check if HITL is enabled for a node and thread.

        Args:
            node_name: Node name
            thread_id: User identifier (from Telegram)

        Returns:
            True if HITL is enabled, False otherwise
        """
        config = self.get_config(thread_id)
        is_enabled = config.is_enabled_for_node(node_name)

        logger.info(
            f"HITL check: node='{node_name}', thread_id='{thread_id}', enabled={is_enabled}"
        )
        return is_enabled

    def get_config(self, thread_id: str) -> HITLConfig:
        """
        Get configuration for a user

        Args:
            thread_id: User identifier

        Returns:
            HITLConfig for the user
        """
        if thread_id not in self._configs:
            # Create default config for new user
            self._configs[thread_id] = HITLConfig()
            logger.info(f"Created default HITL config for thread_id: {thread_id}")

        return self._configs[thread_id]

    def set_config(self, thread_id: str, config: HITLConfig) -> None:
        """
        Set configuration for a user

        Args:
            thread_id: User identifier
            config: New HITL configuration
        """
        self._configs[thread_id] = config
        logger.info(
            f"Updated HITL config for thread_id: {thread_id}, config: {config.to_dict()}"
        )

    def update_node_setting(
        self, thread_id: str, node_name: str, enabled: bool
    ) -> HITLConfig:
        """
        Update setting for a specific node

        Args:
            thread_id: User identifier
            node_name: Name of the node
            enabled: Whether HITL should be enabled for this node

        Returns:
            Updated HITLConfig
        """
        config = self.get_config(thread_id)

        # Update the specific node setting
        if hasattr(config, node_name):
            setattr(config, node_name, enabled)
            self.set_config(thread_id, config)
            logger.info(
                f"Updated node '{node_name}' to {enabled} for thread_id: {thread_id}"
            )
        else:
            logger.warning(
                f"Unknown node name '{node_name}' for thread_id: {thread_id}"
            )

        return config

    def reset_config(self, thread_id: str) -> None:
        """
        Reset configuration to default values

        Args:
            thread_id: User identifier
        """
        self._configs[thread_id] = HITLConfig()
        logger.info(f"Reset HITL config to default for thread_id: {thread_id}")

    def bulk_update(self, thread_id: str, enable_all: bool) -> HITLConfig:
        """
        Enable or disable HITL for all nodes

        Args:
            thread_id: User identifier
            enable_all: Whether to enable or disable all HITL

        Returns:
            Updated HITLConfig
        """
        if enable_all:
            config = HITLConfig.all_enabled()
        else:
            config = HITLConfig.all_disabled()

        self.set_config(thread_id, config)
        logger.info(
            f"Bulk updated HITL to {'enabled' if enable_all else 'disabled'} for thread_id: {thread_id}"
        )

        return config

    def get_all_configs(self) -> Dict[str, HITLConfig]:
        """
        Get all configurations (for debugging)

        Returns:
            Dictionary of all thread configs
        """
        return self._configs.copy()

    def get_default_config(self) -> HITLConfig:
        """
        Get the default configuration

        Returns:
            Default HITLConfig
        """
        return self._default_config


# Singleton instance
_hitl_manager_instance: Optional[HITLManager] = None


def get_hitl_manager() -> HITLManager:
    """
    Get singleton instance of HITLManager

    Returns:
        HITLManager instance
    """
    global _hitl_manager_instance
    if _hitl_manager_instance is None:
        _hitl_manager_instance = HITLManager()
        logger.info("Created new HITLManager singleton instance")
    return _hitl_manager_instance


def reset_hitl_manager() -> None:
    """Reset the singleton instance (mainly for testing)"""
    global _hitl_manager_instance
    _hitl_manager_instance = None
    logger.info("Reset HITLManager singleton instance")
