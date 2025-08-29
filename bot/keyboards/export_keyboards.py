"""Inline keyboards for export functionality."""

from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_export_options_keyboard() -> InlineKeyboardMarkup:
    """Main export menu keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📦 Пакет (финальные)",
                callback_data="export:package:final"
            ),
            InlineKeyboardButton(
                text="📦 Пакет (все)",
                callback_data="export:package:all"
            )
        ],
        [
            InlineKeyboardButton(
                text="📄 Один документ",
                callback_data="export:single"
            )
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Настройки экспорта",
                callback_data="export:settings"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="export:cancel"
            )
        ]
    ])


def get_format_keyboard() -> InlineKeyboardMarkup:
    """Export format selection keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📝 Markdown",
                callback_data="format:markdown"
            ),
            InlineKeyboardButton(
                text="📄 PDF",
                callback_data="format:pdf"
            )
        ],
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data="export:back"
            )
        ]
    ])


def get_document_selection_keyboard() -> InlineKeyboardMarkup:
    """Document selection keyboard for single export."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📝 Синтезированный материал",
                callback_data="doc:synthesized_material"
            )
        ],
        [
            InlineKeyboardButton(
                text="❓ Вопросы для закрепления",
                callback_data="doc:questions"
            )
        ],
        [
            InlineKeyboardButton(
                text="📚 Сгенерированный материал",
                callback_data="doc:generated_material"
            )
        ],
        [
            InlineKeyboardButton(
                text="✏️ Распознанные заметки",
                callback_data="doc:recognized_notes"
            )
        ],
        [
            InlineKeyboardButton(
                text="↩️ Назад",
                callback_data="export:back"
            )
        ]
    ])


def get_sessions_keyboard(sessions: List[dict]) -> InlineKeyboardMarkup:
    """Keyboard for session selection from history."""
    keyboard = []
    
    for session in sessions[:5]:
        keyboard.append([
            InlineKeyboardButton(
                text=session['display_name'],
                callback_data=f"session:{session['session_id']}"
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="export:cancel"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    """Export settings keyboard."""
    current_format = settings.get('default_format', 'markdown')
    current_package = settings.get('default_package_type', 'final')
    
    format_text = "📝 Markdown" if current_format == 'markdown' else "📄 PDF"
    package_text = "Финальные" if current_package == 'final' else "Все документы"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"Формат: {format_text}",
                callback_data="settings:format"
            )
        ],
        [
            InlineKeyboardButton(
                text=f"Пакет: {package_text}",
                callback_data="settings:package"
            )
        ],
        [
            InlineKeyboardButton(
                text="💾 Сохранить",
                callback_data="settings:save"
            ),
            InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="settings:cancel"
            )
        ]
    ])


def get_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Confirmation keyboard for export actions."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да",
                callback_data="confirm:yes"
            ),
            InlineKeyboardButton(
                text="❌ Нет",
                callback_data="confirm:no"
            )
        ]
    ])