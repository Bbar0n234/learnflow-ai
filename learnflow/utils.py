import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List, Literal, Annotated, Union
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage
from jinja2 import Template
from pydantic import BaseModel, Field
import operator

# Загрузка переменных окружения
load_dotenv()

class Config:
    """Класс для загрузки и управления конфигурацией"""
    
    def __init__(self):
        self.prompts_config_path = os.getenv('PROMPTS_CONFIG_PATH', './config/prompts.yaml')
        self.graph_config_path = os.getenv('GRAPH_CONFIG_PATH', './config/graph.yaml')
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
        return graph_conf.get('model_config', {}).get('name', 'gpt-4o')
    
    def ensure_directories(self):
        """Создает необходимые директории"""
        Path(self.main_dir).mkdir(exist_ok=True)
        Path(f"{self.main_dir}/outputs").mkdir(exist_ok=True)

class GapQuestions(BaseModel):
    gap_questions: List[str] = Field(
        ...,
        description="Questions relevant to the exam question, which is either absent or insufficiently covered in the student's study material."
    )

class GapQuestionsHITL(BaseModel):
    next_step: Literal["clarify", "finalize"] = Field(
        ...,
        description="Indicates whether further clarification is needed (clarify) or if the questions are ready for use (finalize)."
    )
    refined_gap_questions: List[str] = Field(
        ...,
        description="Refined questions relevant to the exam question, which is either absent or insufficiently covered in the student's study material."
    )

class GeneralState(BaseModel):
    """Общее состояние для обработки"""
    exam_question: str
    gap_questions: List[str] = []
    gap_q_n_a: Annotated[List[str], operator.add] = []
    generated_material: str = ""
    feedback_messages: List[Union[AIMessage, HumanMessage]] = []

def get_prompt_template(prompt_name: str, config: Config) -> Template:
    """Возвращает шаблон промпта по имени"""
    prompts = config.load_prompts()
    return Template(prompts[prompt_name])

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