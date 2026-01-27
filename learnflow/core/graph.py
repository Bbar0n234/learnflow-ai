"""
Сборка LangGraph workflow для обработки экзаменационных материалов.
Объединяет все узлы в единый граф с правильными переходами.
"""

import logging
from langgraph.graph import StateGraph

from .state import GeneralState
from ..nodes import (
    InputProcessingNode,
    RecognitionNode,
    EditMaterialNode,
    QuestionGenerationNode,
    AnswerGenerationNode,
    PlanningStructureNode,
    SectionGenerationNode,
    DocumentAssemblyNode,
    check_assembly_ready,
    ResearchClassifierNode,
    ResearchAgentNode,
)


logger = logging.getLogger(__name__)


def create_workflow() -> StateGraph:
    """
    Создает и настраивает LangGraph workflow для обработки экзаменационных материалов.

    M2-03 Workflow with Research Agent:
    1. START -> input_processing (анализ пользовательского ввода)
    2. input_processing -> recognition_handwritten (распознавание конспектов)
    3. recognition_handwritten -> research_classifier (классификация: нужен ли research)
    4. research_classifier -> (needs_research?)
       - True: research_agent -> planning_structure
       - False: planning_structure
    5. planning_structure -> (HITL loop or finalize)
    6. planning_structure -> parallel Send -> generate_section (параллельная генерация секций)
    7. generate_section -> document_assembly (сборка финального документа)
    8. document_assembly -> edit_material (итеративное редактирование с HITL)
    9. edit_material -> generating_questions (генерация контрольных вопросов с HITL)
    10. generating_questions -> answer_question (параллельная генерация ответов)
    11. answer_question -> END

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
    logger.info("Creating M2-03 workflow with research agent...")

    # Создаем граф с типизированным состоянием
    workflow = StateGraph(GeneralState)

    # Инициализируем все узлы
    input_processing_node = InputProcessingNode()
    recognition_node = RecognitionNode()
    edit_material_node = EditMaterialNode()
    questions_node = QuestionGenerationNode()
    answers_node = AnswerGenerationNode()
    planning_node = PlanningStructureNode()
    section_gen_node = SectionGenerationNode()
    assembly_node = DocumentAssemblyNode()
    research_classifier_node = ResearchClassifierNode()
    research_agent_node = ResearchAgentNode()

    # Добавляем узлы в граф
    workflow.add_node("input_processing", input_processing_node)
    workflow.add_node("recognition_handwritten", recognition_node)
    workflow.add_node("edit_material", edit_material_node)
    workflow.add_node("generating_questions", questions_node)
    workflow.add_node("answer_question", answers_node)
    workflow.add_node("planning_structure", planning_node)
    workflow.add_node("generate_section", section_gen_node)
    workflow.add_node("check_assembly_ready", check_assembly_ready)
    workflow.add_node("document_assembly", assembly_node)
    workflow.add_node("research_classifier", research_classifier_node)
    workflow.add_node("research_agent", research_agent_node)

    # Ставим входной узел
    workflow.set_entry_point("input_processing")

    # Настраиваем переходы между узлами (все через Command):
    # - input_processing -> recognition_handwritten
    # - recognition_handwritten -> research_classifier
    # - research_classifier -> research_agent | planning_structure
    # - research_agent -> planning_structure
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
        "M2-03 workflow with research agent created successfully"
    )
    return workflow
