import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any
from jinja2 import Template

class Config:
    """Класс для загрузки и управления конфигурацией"""
    
    def __init__(self):
        self.prompts_config_path = os.getenv('PROMPTS_CONFIG_PATH', './configs/prompts.yaml')
        self.graph_config_path = os.getenv('GRAPH_CONFIG_PATH', './configs/graph.yaml')
        self.main_dir = os.getenv('MAIN_DIR', './data')
        
    def load_prompts(self) -> Dict[str, str]:
        """Загружает промпты из YAML файла"""
        with open(self.prompts_config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def load_graph_config(self) -> Dict[str, Any]:
        """Загружает конфигурацию графа из YAML файла"""
        with open(self.graph_config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get_model_name(self) -> str:
        """Возвращает имя модели из graph.yaml"""
        graph_conf = self.load_graph_config()
        return graph_conf.get('model_config', {}).get('name', 'gpt-4.1-mini')
    
    def ensure_directories(self):
        """Создает необходимые директории"""
        Path(self.main_dir).mkdir(exist_ok=True)
        Path(f"{self.main_dir}/outputs").mkdir(exist_ok=True)

def pretty_print_pydantic(pydantic_model) -> str:
    """Красиво форматирует JSON схему Pydantic модели"""
    return json.dumps(pydantic_model.model_json_schema(), indent=4)

def save_general_state_to_markdown(state: Dict[str, Any]) -> str:
    """Сохраняет состояние в формате Markdown"""
    md = []
    md.append(f"# Экзаменационный вопрос\n\n{state['exam_question']}\n")

    if state['generated_material']:
        md.append("## Общий материал\n")
        md.append(state['generated_material'])
        md.append("")

    if state['gap_q_n_a']:
        md.append("## Дополнительные вопросы и ответы")
        for i, qna in enumerate(state['gap_q_n_a'], 1):
            md.append(f"{i}. {qna}")
        md.append("")

    return "\n".join(md) 

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
    config = Config()
    prompts_config = config.load_prompts()
    
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