"""Template loading utilities."""

import os
from typing import Dict, Optional

import yaml

from config import settings


_template_cache: Optional[Dict[str, str]] = None


async def load_template(node_name: str) -> str:
    """Load template from configs/prompts.yaml by node name."""
    global _template_cache
    
    if _template_cache is None:
        await _load_prompts_config()
    
    template_key = f"{node_name}_system_prompt"
    if template_key not in _template_cache:
        raise ValueError(f"Template not found for node: {node_name}")
    
    return _template_cache[template_key]


async def _load_prompts_config() -> None:
    """Load prompts configuration from YAML file."""
    global _template_cache
    
    config_path = settings.prompts_config_path
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Prompts config file not found: {config_path}")
    
    with open(config_path, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    
    _template_cache = config or {}


def clear_cache() -> None:
    """Clear template cache (useful for testing)."""
    global _template_cache
    _template_cache = None