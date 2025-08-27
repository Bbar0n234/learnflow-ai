"""Prompt configuration handlers for Telegram bot"""

import logging
from typing import Optional, Dict, Any

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from telegramify_markdown import markdownify

from ..services.prompt_config_client import get_prompt_config_client
from ..states.prompt_config import PromptConfigStates
from ..keyboards.prompt_keyboards import (
    build_main_menu_keyboard,
    build_profile_category_keyboard,
    build_profiles_keyboard,
    build_placeholder_selection_keyboard,
    build_value_selection_keyboard,
    build_settings_view_keyboard,
    build_reset_confirmation_keyboard,
    format_main_menu_message,
    format_settings_message,
    format_profile_applied_message,
    format_placeholder_updated_message,
)


logger = logging.getLogger(__name__)
router = Router()


# Command handlers

@router.message(Command("configure"))
async def cmd_configure(message: Message, state: FSMContext):
    """
    Main command to open prompt configuration menu
    /configure - show prompt configuration menu
    """
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    client = get_prompt_config_client()
    
    try:
        # Check service health first
        is_healthy = await client.health_check()
        if not is_healthy:
            await message.answer(
                "❌ Сервис конфигурации промптов временно недоступен. Попробуйте позже.",
                parse_mode="HTML"
            )
            return
        
        # Get current user settings
        user_settings = await client.get_user_placeholders(user_id)
        
        # Build and send main menu
        text = format_main_menu_message(user_settings)
        keyboard = build_main_menu_keyboard(user_settings)
        
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.set_state(PromptConfigStates.main_menu)
        
        logger.info(f"Opened prompt config menu for user {user_id}")
    
    except Exception as e:
        logger.error(f"Error opening prompt config for user {user_id}: {e}")
        await message.answer(
            "❌ Ошибка при открытии меню настроек. Попробуйте позже.",
            parse_mode="HTML"
        )


@router.message(Command("reset_prompts"))
async def cmd_reset_prompts(message: Message, state: FSMContext):
    """
    Command to reset prompts to defaults
    /reset_prompts - reset all prompt settings
    """
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    
    # Show confirmation dialog
    text = (
        "⚠️ <b>Подтверждение сброса</b>\n\n"
        "Вы уверены, что хотите сбросить все настройки промптов к дефолтным значениям?\n\n"
        "<i>Это действие нельзя отменить.</i>"
    )
    keyboard = build_reset_confirmation_keyboard()
    
    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.set_state(PromptConfigStates.confirming_reset)
    
    logger.info(f"User {user_id} requested prompt reset")


# Main menu navigation

@router.callback_query(F.data == "prompt_main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Return to main menu"""
    if not callback.from_user:
        return
    
    user_id = callback.from_user.id
    client = get_prompt_config_client()
    
    try:
        # Get current user settings
        user_settings = await client.get_user_placeholders(user_id)
        
        # Update message with main menu
        text = format_main_menu_message(user_settings)
        keyboard = build_main_menu_keyboard(user_settings)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.set_state(PromptConfigStates.main_menu)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error returning to main menu for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке меню", show_alert=True)


@router.callback_query(F.data == "prompt_close")
async def callback_close_menu(callback: CallbackQuery, state: FSMContext):
    """Close the configuration menu"""
    if callback.message:
        await callback.message.delete()
    await state.clear()
    await callback.answer("Меню закрыто")


# Profile selection flow

@router.callback_query(F.data == "prompt_select_profile_category")
async def callback_select_profile_category(callback: CallbackQuery, state: FSMContext):
    """Show profile category selection"""
    try:
        text = (
            "📚 <b>Выбор профиля</b>\n\n"
            "Выберите категорию профилей:\n\n"
            "• <b>Стили изложения</b> - способ подачи материала\n"
            "• <b>Предметные области</b> - специализация по предмету"
        )
        keyboard = build_profile_category_keyboard()
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.set_state(PromptConfigStates.selecting_profile_category)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error showing profile categories: {e}")
        await callback.answer("❌ Ошибка при загрузке категорий", show_alert=True)


@router.callback_query(F.data.startswith("prompt_category_"))
async def callback_show_profiles(callback: CallbackQuery, state: FSMContext):
    """Show profiles for selected category"""
    if not callback.from_user or not callback.data:
        return
    
    user_id = callback.from_user.id
    category = callback.data.replace("prompt_category_", "")
    client = get_prompt_config_client()
    
    try:
        # Get profiles for category
        profiles = await client.get_profiles(category=category)
        
        if not profiles:
            await callback.answer("В этой категории пока нет профилей", show_alert=True)
            return
        
        # Build profile list
        category_name = "Стили изложения" if category == "style" else "Предметные области"
        text = f"📖 <b>{category_name}</b>\n\nВыберите профиль для применения:"
        
        keyboard = build_profiles_keyboard(profiles, category, page=0)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        # Store category in state for pagination
        await state.update_data(current_category=category, profiles=profiles)
        await state.set_state(PromptConfigStates.selecting_profile)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error loading profiles for category {category}: {e}")
        await callback.answer("❌ Ошибка при загрузке профилей", show_alert=True)


@router.callback_query(F.data.startswith("prompt_profiles_page:"))
async def callback_profiles_pagination(callback: CallbackQuery, state: FSMContext):
    """Handle profile list pagination"""
    if not callback.data:
        return
    
    # Parse pagination data
    parts = callback.data.split(":")
    if len(parts) != 3:
        return
    
    category = parts[1]
    page = int(parts[2])
    
    # Get profiles from state
    state_data = await state.get_data()
    profiles = state_data.get("profiles", [])
    
    if not profiles:
        await callback.answer("Список профилей не загружен", show_alert=True)
        return
    
    try:
        # Update keyboard with new page
        keyboard = build_profiles_keyboard(profiles, category, page=page)
        
        if callback.message and hasattr(callback.message, "edit_reply_markup"):
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error paginating profiles: {e}")
        await callback.answer("❌ Ошибка при навигации", show_alert=True)


@router.callback_query(F.data.startswith("prompt_apply_profile:"))
async def callback_apply_profile(callback: CallbackQuery, state: FSMContext):
    """Apply selected profile"""
    if not callback.from_user or not callback.data:
        return
    
    user_id = callback.from_user.id
    profile_id = callback.data.replace("prompt_apply_profile:", "")
    client = get_prompt_config_client()
    
    try:
        # Apply profile
        updated_settings = await client.apply_profile(user_id, profile_id)
        
        # Show success message and return to main menu
        profile_name = updated_settings.active_profile_name or "Неизвестный профиль"
        text = format_profile_applied_message(profile_name)
        
        # Add main menu after short delay
        text += "\n\n" + format_main_menu_message(updated_settings)
        keyboard = build_main_menu_keyboard(updated_settings)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.set_state(PromptConfigStates.main_menu)
        await callback.answer(f"✅ Профиль {profile_name} применен")
        
        logger.info(f"User {user_id} applied profile {profile_id}")
    
    except Exception as e:
        logger.error(f"Error applying profile {profile_id} for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при применении профиля", show_alert=True)


# Placeholder configuration flow

@router.callback_query(F.data == "prompt_select_placeholder")
async def callback_select_placeholder(callback: CallbackQuery, state: FSMContext):
    """Show placeholder selection for detailed configuration"""
    if not callback.from_user:
        return
    
    user_id = callback.from_user.id
    client = get_prompt_config_client()
    
    try:
        # Get current user settings
        user_settings = await client.get_user_placeholders(user_id)
        
        if not user_settings.placeholders:
            await callback.answer("Настройки не загружены", show_alert=True)
            return
        
        # Build placeholder list
        text = (
            "⚙️ <b>Детальная настройка</b>\n\n"
            "Выберите параметр для изменения:"
        )
        keyboard = build_placeholder_selection_keyboard(user_settings.placeholders)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        # Store settings in state for pagination
        await state.update_data(user_settings=user_settings)
        await state.set_state(PromptConfigStates.selecting_placeholder)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error loading placeholders for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке настроек", show_alert=True)




@router.callback_query(F.data.startswith("prompt_edit_placeholder:"))
async def callback_edit_placeholder(callback: CallbackQuery, state: FSMContext):
    """Show value selection for a placeholder"""
    if not callback.from_user or not callback.data:
        return
    
    user_id = callback.from_user.id
    placeholder_id = callback.data.replace("prompt_edit_placeholder:", "")
    client = get_prompt_config_client()
    
    try:
        # Get available values for placeholder
        values = await client.get_placeholder_values(placeholder_id)
        
        if not values:
            await callback.answer("Нет доступных значений", show_alert=True)
            return
        
        # Get current settings to find current value
        user_settings = await client.get_user_placeholders(user_id)
        current_setting = None
        for setting in user_settings.placeholders.values():
            if setting.placeholder_id == placeholder_id:
                current_setting = setting
                break
        
        # Build value selection
        placeholder_name = current_setting.placeholder_display_name if current_setting else "Параметр"
        current_value = current_setting.display_name if current_setting else 'Не установлено'
        
        # Build text with HTML formatting
        text = f"📝 <b>{placeholder_name}</b>\n\n"
        text += f"Текущее значение: <i>{current_value}</i>\n\n"
        text += "Выберите новое значение:"
        
        current_value_id = current_setting.value_id if current_setting else None
        keyboard = build_value_selection_keyboard(
            values, placeholder_id, current_value_id, page=0
        )
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        # Store data in state
        await state.update_data(
            editing_placeholder_id=placeholder_id,
            placeholder_values=values,
            current_value_id=current_value_id
        )
        await state.set_state(PromptConfigStates.selecting_value)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error loading values for placeholder {placeholder_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке значений", show_alert=True)


@router.callback_query(F.data.startswith("prompt_values_page:"))
async def callback_values_pagination(callback: CallbackQuery, state: FSMContext):
    """Handle value list pagination"""
    if not callback.data:
        return
    
    parts = callback.data.split(":")
    if len(parts) != 3:
        return
    
    placeholder_id = parts[1]
    page = int(parts[2])
    
    # Get data from state
    state_data = await state.get_data()
    values = state_data.get("placeholder_values", [])
    current_value_id = state_data.get("current_value_id")
    
    if not values:
        await callback.answer("Значения не загружены", show_alert=True)
        return
    
    try:
        # Update keyboard with new page
        keyboard = build_value_selection_keyboard(
            values, placeholder_id, current_value_id, page=page
        )
        
        if callback.message and hasattr(callback.message, "edit_reply_markup"):
            await callback.message.edit_reply_markup(reply_markup=keyboard)
        
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error paginating values: {e}")
        await callback.answer("❌ Ошибка при навигации", show_alert=True)


@router.callback_query(F.data.startswith("prompt_set_v:"))
async def callback_set_value(callback: CallbackQuery, state: FSMContext):
    """Set new value for placeholder"""
    if not callback.from_user or not callback.data:
        return
    
    user_id = callback.from_user.id
    
    # Get index from callback data
    try:
        index = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Неверный формат данных", show_alert=True)
        return
    
    # Get stored data
    data = await state.get_data()
    if "placeholder_values" not in data or "editing_placeholder_id" not in data:
        await callback.answer("❌ Данные сеанса устарели", show_alert=True)
        return
    
    values = data["placeholder_values"]
    placeholder_id = data["editing_placeholder_id"]
    
    # Check index validity
    if index < 0 or index >= len(values):
        await callback.answer("❌ Неверный индекс значения", show_alert=True)
        return
    
    value = values[index]
    value_id = value.id
    
    client = get_prompt_config_client()
    
    try:
        # Set new value
        await client.set_placeholder(user_id, placeholder_id, value_id)
        
        # Get placeholder name from current settings and value name
        user_settings_before = await state.get_data()
        placeholder_name = "Параметр"
        value_name = value.display_name
        
        # Try to find placeholder display name
        if "user_settings" in user_settings_before:
            settings = user_settings_before["user_settings"]
            for setting in settings.placeholders.values():
                if setting.placeholder_id == placeholder_id:
                    placeholder_name = setting.placeholder_display_name
                    break
        
        # Show success and return to placeholder list
        text = format_placeholder_updated_message(
            placeholder_name,
            value_name
        )
        
        # Get updated settings and show placeholder list
        user_settings = await client.get_user_placeholders(user_id)
        text += "\n\n⚙️ <b>Детальная настройка</b>\n\nВыберите параметр для изменения:"
        keyboard = build_placeholder_selection_keyboard(user_settings.placeholders)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.update_data(user_settings=user_settings)
        await state.set_state(PromptConfigStates.selecting_placeholder)
        await callback.answer(f"✅ Значение обновлено")
        
        logger.info(f"User {user_id} set placeholder {placeholder_id} to {value_id}")
    
    except Exception as e:
        logger.error(f"Error setting placeholder {placeholder_id} for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при сохранении", show_alert=True)


# Settings view

@router.callback_query(F.data == "prompt_view_settings")
async def callback_view_settings(callback: CallbackQuery, state: FSMContext):
    """Show current settings view"""
    if not callback.from_user:
        return
    
    user_id = callback.from_user.id
    client = get_prompt_config_client()
    
    try:
        # Get current settings
        user_settings = await client.get_user_placeholders(user_id)
        
        # Build settings view
        text = format_settings_message(user_settings)
        keyboard = build_settings_view_keyboard(user_settings)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.update_data(user_settings=user_settings)
        await state.set_state(PromptConfigStates.viewing_settings)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error loading settings view for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при загрузке настроек", show_alert=True)


# Reset confirmation

@router.callback_query(F.data == "prompt_reset_confirm")
async def callback_reset_confirm(callback: CallbackQuery, state: FSMContext):
    """Show reset confirmation dialog"""
    try:
        text = (
            "⚠️ **Подтверждение сброса**\n\n"
            "Вы уверены, что хотите сбросить все настройки промптов к дефолтным значениям?\n\n"
            "_Это действие нельзя отменить._"
        )
        keyboard = build_reset_confirmation_keyboard()
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.set_state(PromptConfigStates.confirming_reset)
        await callback.answer()
    
    except Exception as e:
        logger.error(f"Error showing reset confirmation: {e}")
        await callback.answer("❌ Ошибка", show_alert=True)


@router.callback_query(F.data == "prompt_reset_confirmed")
async def callback_reset_confirmed(callback: CallbackQuery, state: FSMContext):
    """Execute reset to defaults"""
    if not callback.from_user:
        return
    
    user_id = callback.from_user.id
    client = get_prompt_config_client()
    
    try:
        # Reset to defaults
        user_settings = await client.reset_to_defaults(user_id)
        
        # Show success and return to main menu
        text = (
            "✅ <b>Настройки сброшены</b>\n\n"
            "Все параметры промптов возвращены к дефолтным значениям.\n\n"
        )
        text += format_main_menu_message(user_settings)
        keyboard = build_main_menu_keyboard(user_settings)
        
        if callback.message and hasattr(callback.message, "edit_text"):
            await callback.message.edit_text(
                text, reply_markup=keyboard, parse_mode="Markdown"
            )
        
        await state.set_state(PromptConfigStates.main_menu)
        await callback.answer("Настройки сброшены")
        
        logger.info(f"User {user_id} reset prompts to defaults")
    
    except Exception as e:
        logger.error(f"Error resetting prompts for user {user_id}: {e}")
        await callback.answer("❌ Ошибка при сбросе настроек", show_alert=True)


# No-op callback for pagination indicators
@router.callback_query(F.data == "prompt_noop")
async def callback_noop(callback: CallbackQuery):
    """No operation callback for non-interactive buttons"""
    await callback.answer()