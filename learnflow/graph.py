"""
Сборка LangGraph workflow для обработки экзаменационных материалов.
Объединяет все узлы в единый граф с правильными переходами.
"""

import logging
from langgraph.graph import StateGraph, START, END

from .state import ExamState
from .nodes.content import ContentGenerationNode
from .nodes.questions import QuestionGenerationNode
from .nodes.answers import AnswerGenerationNode


logger = logging.getLogger(__name__)


def create_workflow() -> StateGraph:
    """
    Создает и настраивает LangGraph workflow для обработки экзаменационных материалов.
    
    Поток выполнения:
    1. START -> generating_content (генерация обучающего материала)
    2. generating_content -> generating_questions (генерация gap questions с HITL)
    3. generating_questions -> answer_question (параллельная генерация ответов)
    4. answer_question -> END
    
    Returns:
        StateGraph: Настроенный граф workflow
    """
    logger.info("Creating exam workflow...")
    
    # Создаем граф с типизированным состоянием
    workflow = StateGraph(ExamState)
    
    # Инициализируем узлы
    content_node = ContentGenerationNode()
    questions_node = QuestionGenerationNode()
    answers_node = AnswerGenerationNode()
    
    # Добавляем узлы в граф
    workflow.add_node("generating_content", content_node)
    workflow.add_node("generating_questions", questions_node)
    workflow.add_node("answer_question", answers_node)
    
    # Настраиваем переходы между узлами
    # START -> генерация контента
    workflow.add_edge(START, "generating_content")
    
    # Остальные переходы управляются через Command в узлах:
    # - generating_content -> generating_questions (Command)
    # - generating_questions -> generating_questions (HITL цикл через Command)
    # - generating_questions -> answer_question (параллельные Send через Command)
    # - answer_question -> END (Command)
    
    logger.info("Exam workflow created successfully")
    return workflow 