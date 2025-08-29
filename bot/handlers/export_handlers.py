"""Export handlers for Telegram bot."""

import logging
import aiohttp
from io import BytesIO
from typing import Optional
from datetime import datetime

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from ..keyboards.export_keyboards import (
    get_export_options_keyboard,
    get_format_keyboard,
    get_document_selection_keyboard,
    get_sessions_keyboard,
    get_settings_keyboard,
    get_confirmation_keyboard,
)

logger = logging.getLogger(__name__)

# Router for export handlers
router = Router()

# Base URL for artifacts service
ARTIFACTS_SERVICE_URL = "http://localhost:8001"


class ExportStates(StatesGroup):
    """States for export flow."""
    selecting_option = State()
    selecting_format = State()
    selecting_document = State()
    selecting_session = State()
    configuring_settings = State()


async def get_user_settings(user_id: str) -> dict:
    """Get user export settings from artifacts service."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                f"{ARTIFACTS_SERVICE_URL}/users/{user_id}/export-settings"
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Failed to get user settings: {e}")
    
    # Return defaults if failed
    return {
        "default_format": "markdown",
        "default_package_type": "final"
    }


async def save_user_settings(user_id: str, settings: dict) -> bool:
    """Save user export settings."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.put(
                f"{ARTIFACTS_SERVICE_URL}/users/{user_id}/export-settings",
                json=settings
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Failed to save user settings: {e}")
    return False


async def export_document(
    thread_id: str,
    session_id: str,
    document_name: str,
    format: str = "markdown"
) -> Optional[bytes]:
    """Export single document from artifacts service."""
    async with aiohttp.ClientSession() as session:
        try:
            params = {
                "document_name": document_name,
                "format": format
            }
            async with session.get(
                f"{ARTIFACTS_SERVICE_URL}/threads/{thread_id}/sessions/{session_id}/export/single",
                params=params
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.error(f"Failed to export document: {e}")
    return None


async def export_package(
    thread_id: str,
    session_id: str,
    package_type: str = "final",
    format: str = "markdown"
) -> Optional[bytes]:
    """Export package of documents from artifacts service."""
    async with aiohttp.ClientSession() as session:
        try:
            params = {
                "package_type": package_type,
                "format": format
            }
            async with session.get(
                f"{ARTIFACTS_SERVICE_URL}/threads/{thread_id}/sessions/{session_id}/export/package",
                params=params
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.error(f"Failed to export package: {e}")
    return None


async def get_recent_sessions(user_id: str, limit: int = 5) -> list:
    """Get recent sessions for user."""
    async with aiohttp.ClientSession() as session:
        try:
            params = {"limit": limit}
            async with session.get(
                f"{ARTIFACTS_SERVICE_URL}/users/{user_id}/sessions/recent",
                params=params
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.error(f"Failed to get recent sessions: {e}")
    return []


@router.message(Command("export"))
async def cmd_export(message: Message, state: FSMContext):
    """Handle /export command - quick export with default settings."""
    user_id = str(message.from_user.id)
    
    # Use user_id as thread_id (same as in main bot logic)
    thread_id = str(user_id)
    
    # Get current session from state
    data = await state.get_data()
    # If no session_id in state, use current timestamp as session_id
    session_id = data.get("current_session_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    
    # Get user settings
    settings = await get_user_settings(user_id)
    
    await message.answer(
        "⏳ Экспортирую документы с настройками по умолчанию..."
    )
    
    # Export with default settings
    content = await export_package(
        thread_id,
        session_id,
        settings["default_package_type"],
        settings["default_format"]
    )
    
    if content:
        # Send file to user
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{timestamp}_export.zip"
        
        file = BufferedInputFile(
            file=content,
            filename=filename
        )
        
        await message.answer_document(
            document=file,
            caption="✅ Документы успешно экспортированы!"
        )
    else:
        await message.answer(
            "❌ Не удалось экспортировать документы. Попробуйте позже."
        )


@router.message(Command("export_menu"))
async def cmd_export_menu(message: Message, state: FSMContext):
    """Handle /export_menu command - show export options."""
    await state.set_state(ExportStates.selecting_option)
    await message.answer(
        "📤 Выберите тип экспорта:",
        reply_markup=get_export_options_keyboard()
    )


@router.message(Command("sessions"))
@router.message(Command("history"))
async def cmd_sessions(message: Message, state: FSMContext):
    """Handle /sessions and /history commands."""
    user_id = str(message.from_user.id)
    
    sessions = await get_recent_sessions(user_id)
    
    if not sessions:
        await message.answer(
            "📚 История сессий пуста.\n"
            "Создайте сессию, отправив вопрос для изучения."
        )
        return
    
    await state.set_state(ExportStates.selecting_session)
    await message.answer(
        "📚 Выберите сессию для экспорта:\n"
        "(показаны последние 5 сессий)",
        reply_markup=get_sessions_keyboard(sessions)
    )


@router.message(Command("export_settings"))
async def cmd_export_settings(message: Message, state: FSMContext):
    """Handle /export_settings command."""
    user_id = str(message.from_user.id)
    settings = await get_user_settings(user_id)
    
    await state.set_state(ExportStates.configuring_settings)
    await state.update_data(export_settings=settings)
    
    await message.answer(
        "⚙️ Настройки экспорта:",
        reply_markup=get_settings_keyboard(settings)
    )


# Callback handlers

@router.callback_query(F.data.startswith("export:"))
async def handle_export_callbacks(callback: CallbackQuery, state: FSMContext):
    """Handle export-related callbacks."""
    action = callback.data.split(":")[1]
    
    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Экспорт отменён.")
        return
    
    if action == "back":
        await state.set_state(ExportStates.selecting_option)
        await callback.message.edit_text(
            "📤 Выберите тип экспорта:",
            reply_markup=get_export_options_keyboard()
        )
        return
    
    if action == "package":
        # Package export selected
        package_type = callback.data.split(":")[2]
        await state.update_data(package_type=package_type)
        await state.set_state(ExportStates.selecting_format)
        
        await callback.message.edit_text(
            f"📦 Экспорт пакета ({'все документы' if package_type == 'all' else 'финальные документы'})\n"
            "Выберите формат:",
            reply_markup=get_format_keyboard()
        )
        return
    
    if action == "single":
        # Single document export
        await state.set_state(ExportStates.selecting_document)
        await callback.message.edit_text(
            "📄 Выберите документ для экспорта:",
            reply_markup=get_document_selection_keyboard()
        )
        return
    
    if action == "settings":
        # Show settings
        user_id = str(callback.from_user.id)
        settings = await get_user_settings(user_id)
        
        await state.set_state(ExportStates.configuring_settings)
        await state.update_data(export_settings=settings)
        
        await callback.message.edit_text(
            "⚙️ Настройки экспорта:",
            reply_markup=get_settings_keyboard(settings)
        )
        return


@router.callback_query(F.data.startswith("format:"))
async def handle_format_selection(callback: CallbackQuery, state: FSMContext):
    """Handle format selection."""
    format_type = callback.data.split(":")[1]
    data = await state.get_data()
    
    # Use user_id as thread_id 
    thread_id = str(callback.from_user.id)
    session_id = data.get("current_session_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
    
    if not thread_id:
        await callback.message.edit_text(
            "❌ Нет активной сессии для экспорта."
        )
        return
    
    await callback.message.edit_text("⏳ Экспортирую документы...")
    
    # Check if package or single export
    if "package_type" in data:
        # Package export
        content = await export_package(
            thread_id,
            session_id,
            data["package_type"],
            format_type
        )
        filename = f"session_export.zip"
    else:
        # Single document export
        document_name = data.get("document_name", "synthesized_material")
        content = await export_document(
            thread_id,
            session_id,
            document_name,
            format_type
        )
        ext = "pdf" if format_type == "pdf" else "md"
        filename = f"{document_name}.{ext}"
    
    if content:
        file = BufferedInputFile(file=content, filename=filename)
        await callback.message.answer_document(
            document=file,
            caption="✅ Документы успешно экспортированы!"
        )
        await callback.message.delete()
    else:
        await callback.message.edit_text(
            "❌ Не удалось экспортировать документы."
        )
    
    await state.clear()


@router.callback_query(F.data.startswith("doc:"))
async def handle_document_selection(callback: CallbackQuery, state: FSMContext):
    """Handle document selection for single export."""
    document_name = callback.data.split(":")[1]
    
    await state.update_data(document_name=document_name)
    await state.set_state(ExportStates.selecting_format)
    
    doc_names = {
        "synthesized_material": "Синтезированный материал",
        "questions": "Вопросы для закрепления",
        "generated_material": "Сгенерированный материал",
        "recognized_notes": "Распознанные заметки"
    }
    
    await callback.message.edit_text(
        f"📄 Экспорт: {doc_names.get(document_name, document_name)}\n"
        "Выберите формат:",
        reply_markup=get_format_keyboard()
    )


@router.callback_query(F.data.startswith("session:"))
async def handle_session_selection(callback: CallbackQuery, state: FSMContext):
    """Handle session selection from history."""
    session_id = callback.data.split(":")[1]
    
    # Get session details
    user_id = str(callback.from_user.id)
    sessions = await get_recent_sessions(user_id)
    
    selected_session = None
    for session in sessions:
        if session["session_id"] == session_id:
            selected_session = session
            break
    
    if not selected_session:
        await callback.message.edit_text(
            "❌ Сессия не найдена."
        )
        return
    
    # Update state with selected session
    await state.update_data(
        thread_id=selected_session["thread_id"],
        current_session_id=session_id
    )
    
    await state.set_state(ExportStates.selecting_option)
    await callback.message.edit_text(
        f"📚 Сессия: {selected_session['display_name']}\n\n"
        "📤 Выберите тип экспорта:",
        reply_markup=get_export_options_keyboard()
    )


@router.callback_query(F.data.startswith("settings:"))
async def handle_settings_callbacks(callback: CallbackQuery, state: FSMContext):
    """Handle settings-related callbacks."""
    action = callback.data.split(":")[1]
    
    if action == "cancel":
        await callback.message.edit_text("❌ Настройки не изменены.")
        await state.clear()
        return
    
    data = await state.get_data()
    settings = data.get("export_settings", {})
    
    if action == "format":
        # Toggle format
        current = settings.get("default_format", "markdown")
        settings["default_format"] = "pdf" if current == "markdown" else "markdown"
        await state.update_data(export_settings=settings)
        
        await callback.message.edit_text(
            "⚙️ Настройки экспорта:",
            reply_markup=get_settings_keyboard(settings)
        )
        return
    
    if action == "package":
        # Toggle package type
        current = settings.get("default_package_type", "final")
        settings["default_package_type"] = "all" if current == "final" else "final"
        await state.update_data(export_settings=settings)
        
        await callback.message.edit_text(
            "⚙️ Настройки экспорта:",
            reply_markup=get_settings_keyboard(settings)
        )
        return
    
    if action == "save":
        # Save settings
        user_id = str(callback.from_user.id)
        settings["user_id"] = user_id
        
        success = await save_user_settings(user_id, settings)
        
        if success:
            await callback.message.edit_text(
                "✅ Настройки сохранены!\n\n"
                f"📝 Формат по умолчанию: {'PDF' if settings['default_format'] == 'pdf' else 'Markdown'}\n"
                f"📦 Тип пакета: {'Все документы' if settings['default_package_type'] == 'all' else 'Финальные документы'}"
            )
        else:
            await callback.message.edit_text(
                "❌ Не удалось сохранить настройки."
            )
        
        await state.clear()


@router.callback_query(F.data.startswith("confirm:"))
async def handle_confirmation(callback: CallbackQuery, state: FSMContext):
    """Handle confirmation callbacks."""
    answer = callback.data.split(":")[1]
    
    if answer == "no":
        await callback.message.edit_text("❌ Действие отменено.")
        await state.clear()
        return
    
    # Handle confirmed action based on state
    current_state = await state.get_state()
    
    # Process confirmed action
    await callback.message.edit_text("✅ Действие подтверждено.")
    await state.clear()