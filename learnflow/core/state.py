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
    display_name: Optional[str] = Field(default=None, description="Краткое название сессии (3-5 слов)")
    
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
    
    # Edit agent fields (minimal for MVP)
    edit_count: int = Field(default=0, description="Total number of edits performed")
    needs_user_input: bool = Field(default=True, description="Flag for HITL interaction")
    agent_message: Optional[str] = Field(default=None, description="Message from edit agent to user")
    last_action: Optional[str] = Field(default=None, description="Type of last action (edit/message/complete)")


# Edit agent structured output models
class ActionDecision(BaseModel):
    """Решение о типе действия для edit agent"""
    action_type: Literal["edit", "message", "complete"] = Field(
        description="Type of action to perform"
    )


class EditDetails(BaseModel):
    """Детали для действия редактирования"""
    old_text: str = Field(description="Exact text to replace")
    new_text: str = Field(description="Replacement text")
    continue_editing: bool = Field(
        default=True,
        description="Continue editing autonomously after this edit"
    )


class EditMessageDetails(BaseModel):
    """Детали для сообщения пользователю от edit agent"""
    content: str = Field(description="Message to send to user")