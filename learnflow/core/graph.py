"""
Сборка LangGraph workflow для обработки экзаменационных материалов.
Объединяет все узлы в единый граф с правильными переходами.
"""

import logging
from langgraph.graph import StateGraph

from .state import GeneralState
from ..nodes import (
    InputProcessingNode,
    ContentGenerationNode,
    RecognitionNode,
    SynthesisNode,
    EditMaterialNode,
    QuestionGenerationNode,
    AnswerGenerationNode,
    PlanningStructureNode,  # M2-01
    SectionGenerationNode,  # M2-01
    DocumentAssemblyNode,  # M2-01
)


logger = logging.getLogger(__name__)


def create_workflow() -> StateGraph:
    """
    Создает и настраивает LangGraph workflow для обработки экзаменационных материалов.

    M2-01 Decomposed generation workflow:
    1. START -> input_processing (анализ пользовательского ввода)
    2. input_processing -> recognition_handwritten (распознавание конспектов РАНЬШЕ планирования)
    3. recognition_handwritten -> planning_structure (планирование структуры с HITL)
    4. planning_structure -> (HITL loop or finalize)
    5. planning_structure -> parallel Send -> generate_section (параллельная генерация секций)
    6. generate_section -> document_assembly (сборка финального документа)
    7. document_assembly -> edit_material (итеративное редактирование с HITL)
    8. edit_material -> generating_questions (генерация контрольных вопросов с HITL)
    9. generating_questions -> answer_question (параллельная генерация ответов)
    10. answer_question -> END

    Legacy workflow (before M2-01, saved for rollback):
    # 1. START -> input_processing
    # 2. input_processing -> generating_content
    # 3. generating_content -> recognition_handwritten
    # 4. recognition_handwritten -> synthesis_material
    # 5. synthesis_material -> edit_material
    # 6. edit_material -> generating_questions
    # 7. generating_questions -> answer_question
    # 8. answer_question -> END

    Returns:
        StateGraph: Настроенный граф workflow
    """
    logger.info("Creating M2-01 workflow with early recognition...")

    # Создаем граф с типизированным состоянием
    workflow = StateGraph(GeneralState)

    # Инициализируем все узлы
    input_processing_node = InputProcessingNode()
    content_node = ContentGenerationNode()  # Legacy - will be replaced by decomposed generation
    recognition_node = RecognitionNode()
    synthesis_node = SynthesisNode()  # Legacy - will be replaced by document_assembly
    edit_material_node = EditMaterialNode()
    questions_node = QuestionGenerationNode()
    answers_node = AnswerGenerationNode()

    # M2-01 новые узлы для декомпозированной генерации
    planning_node = PlanningStructureNode()
    section_gen_node = SectionGenerationNode()
    assembly_node = DocumentAssemblyNode()

    # Добавляем узлы в граф
    workflow.add_node("input_processing", input_processing_node)
    workflow.add_node("generating_content", content_node)  # Legacy
    workflow.add_node("recognition_handwritten", recognition_node)
    workflow.add_node("synthesis_material", synthesis_node)  # Legacy
    workflow.add_node("edit_material", edit_material_node)
    workflow.add_node("generating_questions", questions_node)
    workflow.add_node("answer_question", answers_node)

    # M2-01 новые узлы
    workflow.add_node("planning_structure", planning_node)
    workflow.add_node("generate_section", section_gen_node)
    workflow.add_node("document_assembly", assembly_node)

    # Ставим входной узел
    workflow.set_entry_point("input_processing")

    # Настраиваем переходы между узлами (все через Command):
    # - input_processing -> recognition_handwritten
    # - recognition_handwritten -> planning_structure
    # - planning_structure -> planning_structure (HITL цикл)
    # - planning_structure -> generate_section (параллельные Send)
    # - generate_section -> document_assembly (аккумуляция секций)
    # - document_assembly -> edit_material
    # - edit_material -> edit_material (HITL цикл)
    # - edit_material -> generating_questions
    # - generating_questions -> generating_questions (HITL цикл)
    # - generating_questions -> answer_question (параллельные Send)
    # - answer_question -> END

    logger.info(
        "M2-01 decomposed generation workflow created successfully"
    )
    return workflow
