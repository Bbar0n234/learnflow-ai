"""
Модуль для работы с промптами из YAML файла.
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any
from jinja2 import Template


def load_prompts_config() -> Dict[str, str]:
    """Загружает конфигурацию промптов из YAML файла."""
    config_path = Path(__file__).parent.parent / "config" / "prompts.yaml"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Prompts config file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def render_system_prompt(template_type: str, template_variant: str = "initial", **kwargs: Any) -> str:
    """
    Рендерит системный промпт на основе типа шаблона и варианта.
    
    Args:
        template_type: Тип шаблона (например, 'generating_content')
        template_variant: Вариант шаблона ('initial' или 'further')
        **kwargs: Параметры для подстановки в шаблон
    
    Returns:
        Отрендеренный промпт
    """
    prompts_config = load_prompts_config()
    
    # Формируем ключ для поиска шаблона
    if template_variant == "initial":
        template_key = f"{template_type}_system_prompt"
    else:
        template_key = f"{template_type}_{template_variant}_system_prompt"
    
    # Если специфичный вариант не найден, используем базовый
    if template_key not in prompts_config:
        template_key = f"{template_type}_system_prompt"
    
    if template_key not in prompts_config:
        raise KeyError(f"Template '{template_key}' not found in prompts config")
    
    template_content = prompts_config[template_key]
    template = Template(template_content)
    
    return template.render(**kwargs) 