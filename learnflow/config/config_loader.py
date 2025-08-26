import os
import yaml
from jinja2 import Template
from typing import Dict, Any


def load_yaml_with_env(path: str) -> Dict[str, Any]:
    """
    Загружает YAML-файл с подстановкой переменных окружения через Jinja2.
    
    Args:
        path: Путь к YAML-файлу
        
    Returns:
        dict: Загруженная конфигурация с подставленными переменными
    """
    # Проверяем, является ли файл prompts.yaml
    if path.endswith("prompts.yaml"):
        # Для файла prompts.yaml не рендерим шаблоны Jinja2
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f.read())
    else:
        # Для остальных файлов применяем подстановку переменных окружения
        with open(path, "r", encoding="utf-8") as f:
            template = Template(f.read())
            rendered = template.render(env=os.environ)
            return yaml.safe_load(rendered)