"""
Узлы LangGraph workflow для обработки экзаменационных материалов.
"""

from .content import ContentGenerationNode
from .questions import QuestionGenerationNode
from .answers import AnswerGenerationNode
from .input_processing import InputProcessingNode
from .recognition import RecognitionNode
from .synthesis import SynthesisNode
from .edit_material import EditMaterialNode
from .planning_structure import PlanningStructureNode  # M2-01
from .section_generation import SectionGenerationNode  # M2-01
from .document_assembly import DocumentAssemblyNode, check_assembly_ready  # M2-01
from .research_classifier import ResearchClassifierNode  # M2-03
from .research_agent import ResearchAgentNode  # M2-03

__all__ = [
    "ContentGenerationNode",
    "QuestionGenerationNode",
    "AnswerGenerationNode",
    "InputProcessingNode",
    "RecognitionNode",
    "SynthesisNode",
    "EditMaterialNode",
    "PlanningStructureNode",  # M2-01
    "SectionGenerationNode",  # M2-01
    "DocumentAssemblyNode",  # M2-01
    "check_assembly_ready",  # M2-01
    "ResearchClassifierNode",  # M2-03
    "ResearchAgentNode",  # M2-03
]
