"""
Модели состояния для LangGraph workflow.
Адаптированы из utils.py для production архитектуры.
"""

import operator
from typing import List, Any, Annotated, Literal, Optional
from pydantic import BaseModel, Field


class GapQuestions(BaseModel):
    """Модель для начальной генерации gap questions"""
    
    gap_questions: List[str] = Field(
        ...,
        description="Questions relevant to the exam question, which is either absent or insufficiently covered in the student's study material."
    )


class GapQuestionsHITL(BaseModel):
    """Модель для HITL refinement gap questions"""
    
    next_step: Literal["clarify", "finalize"] = Field(
        ...,
        description="Indicates whether further clarification is needed (clarify) or if the questions are ready for use (finalize)."
    )
    gap_questions: List[str] = Field(
        ..., 
        description="Refined questions relevant to the exam question, which is either absent or insufficiently covered in the student's study material."
    )


class ExamState(BaseModel):
    """
    Основное состояние для workflow обработки экзаменационных материалов.
    Адаптировано из GeneralState с расширениями для production.
    """
    
    # Входные данные
    exam_question: str = Field(default="", description="Исходный экзаменационный вопрос")
    
    # Новые поля для работы с изображениями
    image_paths: List[str] = Field(
        default_factory=list, 
        description="Пути к загруженным изображениям конспектов (пустой список = нет изображений)"
    )
    recognized_notes: str = Field(
        default="", 
        description="Распознанный текст из рукописных конспектов"
    )
    synthesized_material: str = Field(
        default="", 
        description="Финальный синтезированный материал, объединяющий generated_material и recognized_notes"
    )
    
    # Генерированный контент
    generated_material: str = Field(default="", description="Сгенерированный обучающий материал")
    
    # Gap questions
    gap_questions: List[str] = Field(default_factory=list, description="Список дополнительных вопросов")
    
    # Аккумулирующие поля (используют operator.add для объединения)
    gap_q_n_a: Annotated[List[str], operator.add] = Field(
        default_factory=list,
        description="Список сгенерированных вопросов и ответов"
    )
    
    # HITL feedback
    feedback_messages: List[Any] = Field(
        default_factory=list,
        description="История сообщений для HITL взаимодействия"
    )
    
    # Local artifacts storage
    local_session_path: Optional[str] = Field(default=None, description="Путь к сессии в локальном хранилище")
    local_thread_path: Optional[str] = Field(default=None, description="Путь к потоку в локальном хранилище")
    session_id: Optional[str] = Field(default=None, description="Идентификатор сессии")
    local_learning_material_path: Optional[str] = Field(default=None, description="Путь к обучающему материалу")
    local_folder_path: Optional[str] = Field(default=None, description="Путь к папке сессии")
    learning_material_link_sent: bool = Field(default=False, description="Флаг отправки ссылки на материал")