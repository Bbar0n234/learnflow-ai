"""HITL Settings handlers for Telegram bot"""

import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import aiohttp

from ..services.api_client import get_api_client, HITLConfig
from ..keyboards.hitl_keyboards import (
    build_hitl_settings_keyboard,
    format_hitl_status_message
)


logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("hitl"))
async def show_hitl_menu(message: Message, state: FSMContext):
    """
    Main HITL settings menu
    
    /hitl - show current settings and management menu
    """
    user_id = message.from_user.id
    api_client = get_api_client()
    
    try:
        # Get current HITL configuration
        config = await api_client.get_hitl_config(user_id)
        
        # Format status message
        status_message = format_hitl_status_message(config)
        
        # Build keyboard
        keyboard = build_hitl_settings_keyboard(config)
        
        await message.answer(
            status_message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        logger.info(f"Showed HITL menu for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error showing HITL menu for user {user_id}: {e}")
        await message.answer(
            "❌ Ошибка при получении настроек HITL. Попробуйте позже.",
            parse_mode="Markdown"
        )




@router.callback_query(F.data.startswith("hitl_toggle_"))
async def toggle_node_hitl(callback: CallbackQuery):
    """Toggle HITL for a specific node"""
    user_id = callback.from_user.id
    api_client = get_api_client()
    
    # Extract node name from callback data
    node_name = callback.data.replace("hitl_toggle_", "")
    
    try:
        # Toggle the node setting
        updated_config = await api_client.toggle_node_hitl(user_id, node_name)
        
        # Update the message with new configuration
        status_message = format_hitl_status_message(updated_config)
        keyboard = build_hitl_settings_keyboard(updated_config)
        
        await callback.message.edit_text(
            status_message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        # Show confirmation
        node_display_name = {
            "edit_material": "Редактирование материала",
            "generating_questions": "Генерация вопросов"
        }.get(node_name, node_name)
        
        new_status = "включен" if getattr(updated_config, node_name) else "отключен"
        await callback.answer(f"✅ {node_display_name}: {new_status}")
        
        logger.info(f"Toggled {node_name} for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error toggling {node_name} for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при изменении настройки", show_alert=True)




@router.callback_query(F.data == "hitl_preset_autonomous")
async def set_autonomous_preset(callback: CallbackQuery):
    """Set autonomous preset (all HITL disabled)"""
    user_id = callback.from_user.id
    api_client = get_api_client()
    
    try:
        # Disable all HITL
        updated_config = await api_client.bulk_update_hitl(user_id, False)
        
        # Show updated settings
        status_message = format_hitl_status_message(updated_config)
        keyboard = build_hitl_settings_keyboard(updated_config)
        
        await callback.message.edit_text(
            status_message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await callback.answer("❌ Все узлы выключены")
        logger.info(f"Disabled all HITL for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error disabling all HITL for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при отключении узлов", show_alert=True)


@router.callback_query(F.data == "hitl_preset_guided")
async def set_guided_preset(callback: CallbackQuery):
    """Set guided preset (all HITL enabled)"""
    user_id = callback.from_user.id
    api_client = get_api_client()
    
    try:
        # Enable all HITL
        updated_config = await api_client.bulk_update_hitl(user_id, True)
        
        # Show updated settings
        status_message = format_hitl_status_message(updated_config)
        keyboard = build_hitl_settings_keyboard(updated_config)
        
        await callback.message.edit_text(
            status_message,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        await callback.answer("✅ Все узлы включены")
        logger.info(f"Enabled all HITL for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error enabling all HITL for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при включении узлов", show_alert=True)




# Helper function for other handlers to get HITL status message
async def get_hitl_status_for_user(user_id: int) -> Optional[str]:
    """
    Get formatted HITL status message for a user
    
    Args:
        user_id: Telegram user ID
        
    Returns:
        Optional[str]: Formatted status message or None on error
    """
    try:
        api_client = get_api_client()
        config = await api_client.get_hitl_config(user_id)
        
        edit_status = "✅" if config.edit_material else "❌"
        questions_status = "✅" if config.generating_questions else "❌"
        
        return (
            f"📋 **Режим обработки:**\n"
            f"• Редактирование: {edit_status}\n"
            f"• Генерация вопросов: {questions_status}\n\n"
            f"_Изменить: /hitl_"
        )
        
    except Exception as e:
        logger.error(f"Error getting HITL status for user {user_id}: {e}")
        return None