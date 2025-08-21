"""
Сборка LangGraph workflow для обработки экзаменационных материалов.
Объединяет все узлы в единый граф с правильными переходами.
"""

import logging
from langgraph.graph import StateGraph

from .state import ExamState
from ..nodes import (
    InputProcessingNode,
    ContentGenerationNode,
    RecognitionNode,
    SynthesisNode,
    EditMaterialNode,
    QuestionGenerationNode,
    AnswerGenerationNode,
)


logger = logging.getLogger(__name__)


def create_workflow() -> StateGraph:
    """
    Создает и настраивает LangGraph workflow для обработки экзаменационных материалов.

    Новый поток выполнения с поддержкой изображений и редактирования:
    1. START -> input_processing (анализ пользовательского ввода)
    2. input_processing -> generating_content (генерация обучающего материала)
    3. generating_content -> recognition_handwritten (распознавание конспектов с HITL)
    4. recognition_handwritten -> synthesis_material (синтез финального материала)
    5. synthesis_material -> edit_material (итеративное редактирование с HITL)
    6. edit_material -> generating_questions (генерация gap questions с HITL)
    7. generating_questions -> answer_question (параллельная генерация ответов)
    8. answer_question -> END

    Returns:
        StateGraph: Настроенный граф workflow
    """
    logger.info("Creating enhanced exam workflow with image recognition...")

    # Создаем граф с типизированным состоянием
    workflow = StateGraph(ExamState)

    # Инициализируем все узлы
    input_processing_node = InputProcessingNode()
    content_node = ContentGenerationNode()
    recognition_node = RecognitionNode()
    synthesis_node = SynthesisNode()
    edit_material_node = EditMaterialNode()
    questions_node = QuestionGenerationNode()
    answers_node = AnswerGenerationNode()

    # Добавляем узлы в граф
    workflow.add_node("input_processing", input_processing_node)
    workflow.add_node("generating_content", content_node)
    workflow.add_node("recognition_handwritten", recognition_node)
    workflow.add_node("synthesis_material", synthesis_node)
    workflow.add_node("edit_material", edit_material_node)
    workflow.add_node("generating_questions", questions_node)
    workflow.add_node("answer_question", answers_node)

    # Ставим входной узел
    workflow.set_entry_point("input_processing")

    # Настраиваем переходы между узлами:
    # - input_processing -> generating_content (Command)
    # - generating_content -> recognition_handwritten (Command)
    # - recognition_handwritten -> synthesis_material (Command, с HITL циклом)
    # - synthesis_material -> edit_material (Command)
    # - edit_material -> edit_material (HITL цикл для итеративных правок)
    # - edit_material -> generating_questions (Command после завершения)
    # - generating_questions -> generating_questions (HITL цикл через Command)
    # - generating_questions -> answer_question (параллельные Send через Command)
    # - answer_question -> END (Command)

    logger.info(
        "Enhanced exam workflow created successfully with image recognition support"
    )
    return workflow
