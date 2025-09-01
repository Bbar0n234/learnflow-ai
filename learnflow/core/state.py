"""
Модели состояния для LangGraph workflow.
"""

import operator
from typing import List, Any, Annotated, Literal, Optional
from pydantic import BaseModel, Field


class Questions(BaseModel):
    """Модель для генерации вопросов"""

    questions: List[str] = Field(
        ...,
        description="Questions relevant to the exam question, which is either absent or insufficiently covered in the student's study material.",
    )


class QuestionsHITL(BaseModel):
    """Модель для улучшения текущих вопросов"""

    next_step: Literal["clarify", "finalize"] = Field(
        ...,
        description="Indicates whether further clarification is needed (clarify) or if the questions are ready for use (finalize).",
    )
    questions: List[str] = Field(
        ...,
        description="Refined questions relevant to the exam question, which is either absent or insufficiently covered in the student's study material.",
    )


class GeneralState(BaseModel):
    """
    Основное состояние для workflow обработки материалов.
    """

    # Входные данные
    input_content: str = Field(
        default="", description="Входной контент для составления материала"
    )
    display_name: Optional[str] = Field(
        default=None, description="Краткое название сессии (3-5 слов)"
    )

    # Новые поля для работы с изображениями
    image_paths: List[str] = Field(
        default_factory=list,
        description="Пути к загруженным изображениям конспектов (пустой список = нет изображений)",
    )
    recognized_notes: str = Field(
        default="", description="Распознанный текст из рукописных конспектов"
    )
    synthesized_material: str = Field(
        default="",
        description="Финальный синтезированный материал, объединяющий generated_material и recognized_notes",
    )

    # Генерированный контент
    generated_material: str = Field(
        default="", description="Сгенерированный обучающий материал"
    )

    # Questions
    questions: List[str] = Field(
        default_factory=list, description="Список дополнительных вопросов"
    )

    # Аккумулирующие поля (используют operator.add для объединения)
    questions_and_answers: Annotated[List[str], operator.add] = Field(
        default_factory=list, description="Список сгенерированных вопросов и ответов"
    )

    # HITL feedback
    feedback_messages: List[Any] = Field(
        default_factory=list, description="История сообщений для HITL взаимодействия"
    )
    
    # Edit agent fields (minimal for MVP)
    edit_count: int = Field(default=0, description="Total number of edits performed")
    needs_user_input: bool = Field(
        default=True, description="Flag for HITL interaction"
    )
    agent_message: Optional[str] = Field(
        default=None, description="Message from edit agent to user"
    )
    last_action: Optional[str] = Field(
        default=None, description="Type of last action (edit/message/complete)"
    )


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
        default=True, description="Continue editing autonomously after this edit"
    )


class EditMessageDetails(BaseModel):
    """Детали для сообщения пользователю от edit agent"""

    content: str = Field(description="Message to send to user")
