"""Keyboard layouts for HITL settings management"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ..services.api_client import HITLConfig


def build_hitl_settings_keyboard(config: HITLConfig) -> InlineKeyboardMarkup:
    """
    Build HITL settings keyboard with current state

    Layout:
    [🎯 Редактирование материала: ✅/❌]
    [🎯 Генерация вопросов: ✅/❌]
    [❌ Выключить все узлы] [✅ Включить все узлы]

    Args:
        config: Current HITL configuration

    Returns:
        InlineKeyboardMarkup: Keyboard for HITL settings
    """
    # Node toggle buttons - one per row for better readability
    keyboard = []

    # Edit material node
    edit_status = "✅" if config.edit_material else "❌"
    keyboard.append(
        [
            InlineKeyboardButton(
                text=f"🎯 Редактирование материала: {edit_status}",
                callback_data="hitl_toggle_edit_material",
            )
        ]
    )

    # Question generation node
    questions_status = "✅" if config.generating_questions else "❌"
    keyboard.append(
        [
            InlineKeyboardButton(
                text=f"🎯 Генерация вопросов: {questions_status}",
                callback_data="hitl_toggle_generating_questions",
            )
        ]
    )

    # Preset buttons - two per row
    keyboard.append(
        [
            InlineKeyboardButton(
                text="❌ Выключить все узлы", callback_data="hitl_preset_autonomous"
            ),
            InlineKeyboardButton(
                text="✅ Включить все узлы", callback_data="hitl_preset_guided"
            ),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def format_hitl_status_message(config: HITLConfig) -> str:
    """
    Format HITL status message

    Args:
        config: Current HITL configuration

    Returns:
        str: Formatted status message
    """
    edit_status = "✅ Включено" if config.edit_material else "❌ Отключено"
    questions_status = "✅ Включена" if config.generating_questions else "❌ Отключена"

    # Determine mode
    if config.edit_material and config.generating_questions:
        mode = "🎛️ Управляемый режим"
    elif not config.edit_material and not config.generating_questions:
        mode = "🚀 Автономный режим"
    else:
        mode = "⚙️ Пользовательский режим"

    message = (
        f"📋 **Текущие настройки HITL**\n\n"
        f"**Режим:** {mode}\n\n"
        f"• **Редактирование материала:** {edit_status}\n"
        f"• **Генерация вопросов:** {questions_status}\n\n"
        f"_Используйте кнопки ниже для изменения настроек_"
    )

    return message
